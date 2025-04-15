from fastapi import Request, FastAPI, File, UploadFile, HTTPException, Form, Depends  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from typing import List  # type: ignore
import cloudinary  # type: ignore
import cloudinary.uploader  # type: ignore
import cloudinary.api #type: ignore
from pydantic import BaseModel #type: ignore
from pymongo import MongoClient  # type: ignore
from passlib.context import CryptContext  # type: ignore
import shutil 
import easyocr #type: ignore
from utils.predictor import load_model, predict_quality_from_urls  # type: ignore
from dotenv import load_dotenv # type: ignore
import os
import re  # For email validation
from bson import ObjectId #type: ignore


load_dotenv()

# MongoDB
mongo_uri = os.getenv("DATABASE_URL")
client = MongoClient(mongo_uri)
db = client["bookstore"]  # Make sure you have the correct database name
users_collection = db["users"]  # Collection for users
books_collection = db["books_collection"] 
cart = db["cart"]

# Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to your frontend origin in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model once at the start of the application to avoid reloading it for each request

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialize EasyOCR reader (English)

def extract_price_from_text(text):
    matches = re.findall(r'₹?\s?(\d{2,5})', text)
    if matches:
        return matches[0]
    return None

@app.post("/extract-price")
async def extract_price(price_image: UploadFile = File(...)):
    reader = easyocr.Reader(['en'], gpu=False)
    try:
        # Save uploaded image temporarily
        image_path = f"temp_{price_image.filename}"
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(price_image.file, buffer)

        # Run OCR
        result = reader.readtext(image_path, detail=0)
        combined_text = " ".join(result)
        print("OCR Result:", combined_text)

        # Try to extract price from text
        extracted_price = extract_price_from_text(combined_text)

        # Remove temp file
        os.remove(image_path)

        return {"extracted_price": extracted_price}

    except Exception as e:
        print("Error:", e)
        return {"extracted_price": None}
    

# Email validation regex (checks for @gmail.com)
def validate_email(email: str):
    email_regex = r"^[a-zA-Z0-9_.+-]+@gmail\.com$"
    if not re.match(email_regex, email):
        raise HTTPException(status_code=400, detail="Email must end with @gmail.com")

# Password validation (checks if it's at least 8 characters long)
def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    
@app.get("/user-profile")
async def get_user_profile(email: str):
    # Fetch the user details from the users collection using email
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Return user data excluding the password
    user_data = {
        "name": user["name"],
        "email": user["email"],
        "role": user["role"]
    }
    print(user_data)
    return {"user": user_data}


@app.post("/add-to-cart")
async def add_to_cart(email: str = Form(...), reference_id: str = Form(...)):
    # Debug: Check if email and reference_id are being received correctly
    print(f"Received email: {email}, reference_id: {reference_id}")

    # Find the user in the database
    user = users_collection.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find the book in the database
    book = books_collection.find_one({"reference_id": reference_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Check if the book is already in the user's cart
    existing_item = cart.find_one({"email": email, "reference_id": reference_id})

    if existing_item:
        raise HTTPException(status_code=400, detail="Book already in cart")

    # Add the book to the cart collection
    cart.insert_one({
        "email": email,
        "reference_id": reference_id,
        "book_name": book["book_name"],
        "author_name": book["author_name"],
        "final_price": book["final_price"],
        "book_images": book["book_images"],
    })

    return {"message": "Book added to cart successfully"}

@app.post("/upload-profile-image")
async def upload_profile_image(image: UploadFile = File(...)):
    try:
        # Upload image to Cloudinary
        result = cloudinary.uploader.upload(image.file, folder="profile_images")
        image_url = result["secure_url"]

        # Return the image URL for the frontend
        return {"image_url": image_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")
    
@app.get("/cart")
async def get_cart(email: str):
    cart_items = list(db["cart"].find({"email": email}))

    # Convert ObjectId to string
    for item in cart_items:
        item["_id"] = str(item["_id"])  # Convert ObjectId to string
    
    return {"cart_items": cart_items}


@app.delete("/remove-from-cart")
async def remove_from_cart_by_reference(email: str, reference_id: str):
    result = cart.delete_one({"email": email, "reference_id": reference_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Book not found in cart")
    
    return {"message": "Book removed from cart successfully"}

@app.get("/seller/books")
def get_books_by_seller(email: str):
    books = list(books_collection.find({"email": email}, {"_id": 0}))
    return {"books": books}

@app.get("/books")
def get_books():
    books = list(books_collection.find({}, {"_id": 0}))    
    for book in books:
        book["book_images"] = [url for url in book.get("book_images", [])]
    
    return {"books": books}

@app.get("/book/{book_name}")
def get_book_details(book_name: str):
    print(f"Fetching details for book_name: {book_name}")  # Debugging line
    book = books_collection.find_one({"book_name": book_name}, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    return book


@app.delete("/seller/book/{reference_id}")
def delete_book(reference_id: str):
    book = books_collection.find_one({"reference_id": reference_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    image_urls = book.get("book_images", [])
    public_ids = []
    for url in image_urls:
        parts = url.split("/")
        folder = parts[-2]
        filename = parts[-1].split(".")[0]
        public_ids.append(f"{folder}/{filename}")

    delete_result = cloudinary.api.delete_resources(public_ids)
    books_collection.delete_one({"reference_id": reference_id})
    return {"message": "Book deleted successfully", "cloudinary_delete": delete_result}

@app.post("/store-book-details")
async def store_book_details(
    
    email: str = Form(...),
    publication_year: int = Form(...),
    cost_price: float = Form(...),
    book_images: List[UploadFile] = File(...),
):
    model = load_model()
    print(f"Received email: {email}")
    print(f"Received publication_year: {publication_year}")
    print(f"Received cost_price: {cost_price}")
    print(f"Received {len(book_images)} book images")
    
    # Upload images to Cloudinary
    image_urls = []
    public_ids = []

    # Upload images to Cloudinary
    for image in book_images:
        result = cloudinary.uploader.upload(image.file, folder="book_images")
        image_urls.append(result["secure_url"])
        public_ids.append(result["public_id"])

    # Predict quality
    quality_percentage = predict_quality_from_urls(model, image_urls)

    # Delete uploaded images using cloudinary.api.delete_resources
    delete_response = cloudinary.api.delete_resources(public_ids)
    print(f"Deleted images: {delete_response}")
    # Calculate quality from images
    quality_percentage = predict_quality_from_urls(model, image_urls)

    # Calculate final price based on quality
    final_price = (cost_price * quality_percentage) / 100

    return JSONResponse(content={"final_price": final_price})

@app.post("/upload-book")
async def upload_book_for_sale(
    email: str = Form(...),
    publication_year: int = Form(...),
    cost_price: float = Form(...),
    book_name: str = Form(...),
    book_description: str = Form(...),
    author_name: str = Form(...),
    final_price: float = Form(...),
    reference_id: str = Form(...),  # ✅ Add this line
    book_images: List[UploadFile] = File(...),
):
    # Upload images to Cloudinary and store their URLs
    image_urls = []
    for image in book_images:
        result = cloudinary.uploader.upload(image.file, folder="book_images")
        image_urls.append(result["secure_url"])

    # Store book details in MongoDB with image URLs and reference ID
    book_data = {
        "email": email,
        "publication_year": publication_year,
        "cost_price": cost_price,
        "book_name": book_name,
        "book_description": book_description,
        "author_name": author_name,
        "final_price": final_price,
        "reference_id": reference_id,  # ✅ Store reference ID
        "book_images": image_urls,
    }

    books_collection.insert_one(book_data)

    return {"message": "Book successfully uploaded for sale."}

@app.post("/predict")
async def predict(images: List[UploadFile] = File(...)):
    urls = []
    model = load_model()
    for img in images:
        result = cloudinary.uploader.upload(img.file, folder="book_images")
        urls.append(result["secure_url"])

    quality = predict_quality_from_urls(model, urls)
    print(quality)
    return JSONResponse(content={"quality_percent": quality})

@app.post("/signup")
async def signup(name: str = Form(...), email: str = Form(...), password: str = Form(...), role: str = Form(...)):
    # Log the incoming data to verify
    print(f"Received signup data: {name}, {email}, {role}")
    
    validate_email(email)
    validate_password(password)

    if users_collection.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")

    hashed_password = pwd_context.hash(password)
    users_collection.insert_one({
        "name": name,
        "email": email,
        "password": hashed_password,
        "role": role
    })
    return {"message": "Signup successful"}

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    # Validate email
    validate_email(email)

    user = users_collection.find_one({"email": email})
    if user and pwd_context.verify(password, user["password"]):
        return {
            "message": "Login successful",
            "user": {
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")
