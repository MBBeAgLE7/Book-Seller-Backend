# utils/predictor.py

import torch
from torchvision import models, transforms
from PIL import Image
import requests
from io import BytesIO

def load_model(model_path="model/book_quality_model.pth"):
    model = models.resnet18(pretrained=False)
    model.fc = torch.nn.Linear(model.fc.in_features, 1)
    model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
    model.eval()
    return model

def predict_quality_from_urls(model, urls):
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor()
    ])

    results = []
    for url in urls:
        response = requests.get(url)
        image = Image.open(BytesIO(response.content)).convert("RGB")
        tensor = transform(image).unsqueeze(0)

        with torch.no_grad():
            output = model(tensor)
            quality = output.item() * 2
            results.append(round(quality, 2))

    return round(sum(results) / len(results), 2)
