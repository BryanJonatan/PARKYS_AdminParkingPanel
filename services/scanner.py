import cv2
import pytesseract
import numpy as np
import re
from collections import Counter, deque

# --- CONFIG ---
# Pastikan path tesseract sesuai dengan lokasi install di Raspberry Pi
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

def koreksi_final(text):
    """Fungsi koreksi khusus format Indonesia"""
    clean = "".join([c for c in text if c.isalnum()]).upper()
   
    match = re.search(r'([A-Z0-9]{1,2})([A-Z0-9]{1,4})([A-Z0-9]{0,3})', clean)
    if match:
        p, n, s = match.group(1), match.group(2), match.group(3)
      
        p = p.replace('0', 'O').replace('1', 'I').replace('4', 'A').replace('5', 'S').replace('8', 'B')
      
        n = n.replace('I', '1').replace('L', '1').replace('O', '0').replace('D', '0').replace('S', '5').replace('B', '8').replace('A', '4')
    
        s = s.replace('0', 'O').replace('1', 'I').replace('4', 'A').replace('5', 'S')
        return f"{p} {n} {s}".strip()
    return None

def preprocess_plate(img):
    """Pre-processing gambar untuk meningkatkan akurasi Tesseract"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                 cv2.THRESH_BINARY_INV, 11, 2)
    return thresh

def scan_plate(cap, max_attempts=150):
    """
    Fungsi Scan dengan sistem Voting.
    Menggunakan 'cap' dari app.py agar tidak conflict resource.
    """
    print("[SCANNER] Memulai OCR dari stream aktif...")
    
  
    hasil_history = deque(maxlen=10)
    detected_plate = None
    
    # Config Tesseract: OCR Engine Mode 3 (Default), Page Segmentation Mode 7 (Single Line)
    config_tess = r'--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

    for i in range(max_attempts):
        ret, frame = cap.read()
        if not ret:
            continue

        
        h, w, _ = frame.shape
        x1, y1, x2, y2 = int(w*0.15), int(h*0.35), int(w*0.85), int(h*0.65)
        roi = frame[y1:y2, x1:x2]

        
        thresh = preprocess_plate(roi)
        
        
        raw_text = pytesseract.image_to_string(cv2.bitwise_not(thresh), config=config_tess).strip()
        clean_text = koreksi_final(raw_text)

        if clean_text:
            hasil_history.append(clean_text)
            
            
            if len(hasil_history) > 0:
              
                data_voting = Counter(hasil_history).most_common(1)
                most_common = data_voting[0][0]
                count = data_voting[0][1]
                
                
                if count >= 6:
                    print(f"[SCANNER] FIXED: {most_common} (Confidence: {count*10}%)")
                    detected_plate = most_common
                    break
        
       
        if i % 50 == 0:
            print(f"[SCANNER] Scanning... Attempt {i}/{max_attempts}")

    return detected_plate