from flask import request, redirect, url_for, flash, render_template
from datetime import datetime
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification



model_path = "app/model_v3"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = model.to(device)
model.eval()

label_map = {
    0: "Network issues",
    1: "Software Management",
    2: "Account Management",
    3: "Password issues",
    4: "Security incidents",
    5: "File and Storage management",
    6: "Application Management"
}

def predict(text):
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}  

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    probs = torch.softmax(logits, dim=1)
    predicted_class_id = torch.argmax(probs, dim=1).item()
    predicted_label = label_map[predicted_class_id]
    #return predicted_label, probs[0][predicted_class_id].item()
    return predicted_class_id, predicted_label, probs[0][predicted_class_id].item()

