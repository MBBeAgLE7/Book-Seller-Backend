#!/bin/bash
pip install --upgrade pip
pip install -r requirements.txt
python uvicorn main:app --host 0.0.0.0 --port 10000
