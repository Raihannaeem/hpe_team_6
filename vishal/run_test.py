import os
import json
from dotenv import load_dotenv

# Load env variables FIRST
load_dotenv()

from core.extractor import parse_datasheet_chunks
from core.pdf_processor import process_pdf_from_folder

def main():
    # 1. Load static features
    with open("data/component_features.json", "r") as f:
        feature_cache = json.load(f)
    
    # For now, hardcode to Audio Codec. 
    # Later, you will use PyPDF2 on pages 1-3 to detect this dynamically.
    component_type = "Audio Codec" 
    target_specs = feature_cache.get(component_type, [])

    # 2. Setup the datasheets directory
    datasheet_dir = "datasheets"
    if not os.path.exists(datasheet_dir):
        os.makedirs(datasheet_dir)
        
    # Get all PDFs in the folder
    pdf_files = [f for f in os.listdir(datasheet_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        print(f"⚠️ No PDFs found! Please drag and drop a datasheet into the '{datasheet_dir}' folder and run again.")
        return

    # 3. Process the first PDF in the folder
    pdf_path = os.path.join(datasheet_dir, pdf_files[0])
    
    # Run Stage 1 & 2: pdfplumber extraction and filtering
    real_filtered_chunks = process_pdf_from_folder(pdf_path)

    if not real_filtered_chunks:
        print("No valid data extracted from PDF.")
        return

    # 4. Run Stage 3: The LLM Early-Exit Extractor
    final_hybrid_specs = parse_datasheet_chunks(
        filtered_chunks=real_filtered_chunks, 
        required_features=target_specs,
        component_name=os.path.basename(pdf_path)
    )
    
    # 5. Display Results
    print("\n==========================================")
    print("         FINAL EXTRACTED FEATURES         ")
    print("==========================================")
    print(json.dumps(final_hybrid_specs, indent=2))

if __name__ == "__main__":
    main()