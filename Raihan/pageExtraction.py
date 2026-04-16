#write code to extract text from a pdf file using the PyPDF2 library
import PyPDF2
import fitz  # PyMuPDF
from mistralai.client import Mistral
import json
import os

def send_to_mistral(text):
    with Mistral(api_key=os.getenv("MISTRAL_API_KEY")) as mistral:

        # res = mistral.models.list()
        # print(res)
        # print()
        res = mistral.chat.complete(model="mistral-large-latest", messages=[
            {
                "role": "user",
                "content": text,
            },
        ], stream=False, response_format={
            "type": "text",
        })

        return res

prompt = """Given the text chunk after "start of text chunk" parse the text chunk and extract the given attributes and send it back as json, if you weren't able to find something, replace it with "NF" and if it is not applicable, replace with "NA", return only the json as a string
min_input_voltage
max_input_voltage
min_output_voltage
max_output_voltage
dropout_voltage
max_output_current
quiescent_current
thermal_resistance
min_junction_temperature
max_junction_temperature

start of text chunk
"""

def save_page_as_image(pdf_path, ranked_graph_pages,n):
    base_path = "graphImage"
    path_list = []
    doc = fitz.open(pdf_path)

    for i in range(2):
        page = doc[ranked_graph_pages[i][0]]  # 0-indexed
        print(i)
        pix = page.get_pixmap(dpi=300)  # high resolution
        pix.save(base_path + f"_page_{i+1}.png")  # save as PNG
        # print(f"Saved page {i+1} as image.")
        path_list.append(base_path + f"_page_{i+1}.png")

    return path_list

def send_images_to_llm(image_paths):
    # This function is a placeholder for sending images to the LLM and getting the response.
    # You would need to implement the actual logic to send images and receive responses.
    i = 5

def extract_text_from_pdf(pdf_path):
    text = []
    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)
        for page in pdf_reader.pages:
            # print(page)
            text.append(page.extract_text())
    return text

def rank_pages_by_relevance(extracted_text):
    relevance_scores = []
    keywords = ['voltage', 'current', 'thermal', 'thermal', 'thermal', 'resistance', 'input', 'output', 'junction', 'efficiency', 'frequency', 'temperature', 'dropout', 'dropout', 'dropout', 'quiescent', 'quiescent', 'quiescent']
    for page_text in extracted_text:
        score = sum(page_text.lower().count(keyword) for keyword in keywords)
        relevance_scores.append(score)
    ranked_pages = sorted(enumerate(relevance_scores), key=lambda x: x[1], reverse=True)
    return ranked_pages

def return_string_from_ranked_pages(extracted_text, ranked_pages, n=6):
    top_n_texts = ""
    for i in range(min(n, len(ranked_pages))):
        page_index = ranked_pages[i][0]
        top_n_texts += extracted_text[page_index] + "\n\n"
        # print(page_index+1)
    return top_n_texts

def rank_pages_by_graph_keywords(extracted_text):
    graph_keywords = ['vs', 'dropout', 'voltage', 'figure', 'figure']
    relevance_scores = []
    for page_text in extracted_text:
        score = sum(page_text.lower().count(keyword) for keyword in graph_keywords)
        relevance_scores.append(score)
    ranked_graph_pages = sorted(enumerate(relevance_scores), key=lambda x: x[1], reverse=True)
    return ranked_graph_pages

# Example usage
pdf_file_path = "testSheet.pdf"
extracted_text = extract_text_from_pdf(pdf_file_path)
# print(extracted_text[4])
ranked_pages = rank_pages_by_relevance(extracted_text)
ranked_graph_pages = rank_pages_by_graph_keywords(extracted_text)
save_page_as_image(pdf_file_path, ranked_graph_pages, n=2)
# print("Ranked Pages by Graph Keywords (Page Index, Relevance Score):")
# for page_index, score in ranked_graph_pages:
#     print(f"Page {page_index}: {score}")

# print("Ranked Pages (Page Index, Relevance Score):")
# for page_index, score in ranked_pages:
#     print(f"Page {page_index}: {score}")

prompt = prompt + return_string_from_ranked_pages(extracted_text, ranked_pages)
jsonObj = send_to_mistral(prompt).model_dump()['choices'][0]['message']['content']
# print(repr(jsonObj[8:-4]))

data = json.loads(jsonObj[8:-4])
print(data)