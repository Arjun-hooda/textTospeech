import tkinter as tk
from tkinter import messagebox, simpledialog
import spacy
from dateutil import parser
from datetime import datetime, timedelta
from keybert import KeyBERT
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import nltk
from nltk.tokenize import sent_tokenize
from collections import Counter
import base64
from email.mime.text import MIMEText
import vosk
import pyaudio
import json
import threading

kw_extractor = KeyBERT()
is_manual_input = False
is_transcribing = False
stream_lock = threading.Lock()

model = vosk.Model("/Users/arjunhooda/Desktop/vosk-model-small-en-us-0.15")
recognizer = vosk.KaldiRecognizer(model, 16000)

mic = pyaudio.PyAudio()
stream = mic.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
stream.start_stream()

def transcribe_live_audio():
    global is_transcribing
    is_transcribing = True
    transcribed_text = ""
    while is_transcribing:
        try:
            with stream_lock:
                data = stream.read(2048, exception_on_overflow=False)
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                transcribed_text += result['text'] + " "
                update_text_box(transcribed_text)
            else:
                partial_result = json.loads(recognizer.PartialResult())
                update_text_box(transcribed_text + partial_result['partial'])
        except Exception as e:
            if not is_transcribing:
                break
            print(f"Warning: {e}")

def update_text_box(text):
    text_box.delete("1.0", tk.END)
    text_box.insert(tk.END, text)

def start_transcription():
    threading.Thread(target=transcribe_live_audio, daemon=True).start()

def stop_transcription():
    global is_transcribing
    is_transcribing = False
    try:
        with stream_lock:
            if stream.is_active():
                stream.stop_stream()
            stream.close()
        messagebox.showinfo("Info", "Transcription stopped.")
    except Exception as e:
        print(f"Error stopping transcription: {e}")

def convert_relative_date(date_str):
    try:
        return parser.parse(date_str).strftime("%Y-%m-%d")
    except:
        today = datetime.now()
        days_of_week = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6
        }
        date_str_lower = date_str.lower()
        for day, day_index in days_of_week.items():
            if day in date_str_lower:
                current_day = today.weekday()
                days_until_next = (day_index - current_day + 7) % 7 or 7
                new_date = today + timedelta(days=days_until_next)
                return new_date.strftime("%Y-%m-%d")
        return date_str

def extract_events_and_dates(transcribed_text):
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(transcribed_text)
    events_dates = []
    date_str = ""
    for ent in doc.ents:
        if ent.label_ in ["DATE", "TIME"]:
            date_str += " " + ent.text
    date_str = date_str.strip()
    if date_str:
        event_date = convert_relative_date(date_str)
    else:
        event_date = ""
    event_description = ""
    for token in doc:
        if token.pos_ == "VERB":
            event_tokens = [token.text]
            for child in token.subtree:
                if child != token and not child.is_punct:
                    event_tokens.append(child.text)
            event_description = " ".join(event_tokens).strip()
            break
    if event_description:
        shortened_event = kw_extractor.extract_keywords(event_description, keyphrase_ngram_range=(1, 3), stop_words="english", top_n=1)
        if shortened_event:
            event_short = shortened_event[0][0]
        else:
            event_short = event_description
        events_dates.append([event_short, event_date])
    return events_dates

def add_event_to_calendar(event, date):
    flow = InstalledAppFlow.from_client_secrets_file(
        "/Users/arjunhooda/Desktop/client_secret_611064723257-mrocll8kheqnmrb09n3p0k7srkfc9bkt.apps.googleusercontent.com.json",
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    creds = flow.run_local_server(port=0)
    service = build('calendar', 'v3', credentials=creds)
    event_body = {
        'summary': event,
        'start': {'date': date, 'timeZone': 'Asia/Kolkata'},
        'end': {'date': date, 'timeZone': 'Asia/Kolkata'}
    }
    service.events().insert(calendarId='primary', body=event_body).execute()

def summarize_text(text, max_sentences=3):
    sentences = sent_tokenize(text)
    if len(sentences) < 2:
        return "Text too short to summarize."
    words = [word.lower() for word in nltk.word_tokenize(text) if word.isalnum()]
    word_freq = Counter(words)
    sentence_scores = {}
    for sentence in sentences:
        for word in nltk.word_tokenize(sentence.lower()):
            if word in word_freq:
                sentence_scores[sentence] = sentence_scores.get(sentence, 0) + word_freq[word]
    sorted_sentences = sorted(sentence_scores, key=sentence_scores.get, reverse=True)
    summary_sentences = sorted_sentences[:max_sentences]
    summary = "\n".join(f"• {sentence}" for sentence in summary_sentences)
    return summary

def send_email_via_gmail(subject, body, to_emails):
    flow = InstalledAppFlow.from_client_secrets_file(
        "/Users/arjunhooda/Desktop/client_secret_611064723257-mrocll8kheqnmrb09n3p0k7srkfc9bkt.apps.googleusercontent.com.json",
        scopes=['https://www.googleapis.com/auth/gmail.send']
    )
    creds = flow.run_local_server(port=0)
    service = build('gmail', 'v1', credentials=creds)
    message = MIMEText(body)
    message['subject'] = subject
    message['from'] = 'me'
    for to_email in to_emails:
        message['to'] = to_email
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()

def summarize():
    text = text_box.get("1.0", tk.END).strip()
    summary = summarize_text(text)
    text_box.delete("1.0", tk.END)
    text_box.insert(tk.END, summary)

def add_event():
    text = text_box.get("1.0", tk.END).strip()
    events_dates = extract_events_and_dates(text)
    if events_dates:
        for event, date in events_dates:
            add_event_to_calendar(event, date)
        messagebox.showinfo("Success", "Events added to calendar.")
    else:
        messagebox.showinfo("No Events", "No events detected.")

def send_email():
    text = text_box.get("1.0", tk.END).strip()
    recipient = simpledialog.askstring("Input", "Enter recipient email:")
    if recipient:
        send_email_via_gmail("Summary of Transcribed Text", text, [recipient])
        messagebox.showinfo("Success", "Email sent successfully.")

def toggle_input_mode():
    global is_manual_input
    is_manual_input = not is_manual_input
    if is_manual_input:
        toggle_button.config(text="Switch to Voice Transcription")
    else:
        toggle_button.config(text="Switch to Manual Input")

root = tk.Tk()
root.title("Smart Assistant App")

text_box = tk.Text(root, height=15, width=60)
text_box.pack()

transcribe_button = tk.Button(root, text="Start Live Transcription", command=start_transcription)
transcribe_button.pack()

stop_button = tk.Button(root, text="Stop Transcription", command=stop_transcription)
stop_button.pack()

toggle_button = tk.Button(root, text="Switch to Manual Input", command=toggle_input_mode)
toggle_button.pack()

summarize_button = tk.Button(root, text="Summarize Text", command=summarize)
summarize_button.pack()

event_button = tk.Button(root, text="Add Events to Calendar", command=add_event)
event_button.pack()

email_button = tk.Button(root, text="Send Summary via Email", command=send_email)
email_button.pack()

root.mainloop()