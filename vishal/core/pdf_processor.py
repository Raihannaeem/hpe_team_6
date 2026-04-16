import os
import pdfplumber

def process_pdf_from_folder(pdf_path):
    print(f"\n📄 Reading PDF: {os.path.basename(pdf_path)}")
    raw_tables = []
    raw_text = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                
                # 1. Table Extraction (Highest Priority)
                tables = page.extract_tables()
                for table in tables:
                    table_str = str(table)
                    if any(keyword in table_str.lower() for keyword in ['min', 'max', 'typ', 'unit', 'parameter']):
                        raw_tables.append(f"--- Table from Page {i+1} ---\n{table_str}")

                # 2. Text Extraction (Secondary Priority)
                text = page.extract_text()
                if text:
                    if any(keyword in text.lower() for keyword in [' hz', ' mw', ' db', ' snr', ' thd', 'mhz']):
                        raw_text.append(f"--- Text from Page {i+1} ---\n{text}")

        # Combine tables first, then text
        all_raw_chunks = raw_tables + raw_text
        print(f"✂️ Smart Filter found {len(all_raw_chunks)} raw items.")

        # ---------------------------------------------------------
        # NEW BATCHING LOGIC: Combine tiny chunks into MEGA CHUNKS
        # ---------------------------------------------------------
        batched_chunks = []
        current_batch = ""
        
        # 4000 chars is roughly 1000 tokens (very safe and fast for Groq)
        MAX_CHARS_PER_BATCH = 4000 

        for chunk in all_raw_chunks:
            if len(current_batch) + len(chunk) > MAX_CHARS_PER_BATCH:
                batched_chunks.append(current_batch)
                current_batch = chunk + "\n\n"
            else:
                current_batch += chunk + "\n\n"
                
        # Catch the last batch if it has leftover text
        if current_batch.strip():
            batched_chunks.append(current_batch)

        print(f"📦 Batched down to {len(batched_chunks)} large chunks for the LLM to process rapidly.")
        return batched_chunks

    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
        return []