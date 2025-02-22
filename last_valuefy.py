import tkinter as tk
from tkinter import messagebox, simpledialog

import spacy
from dateutil import parser
from datetime import datetime, timedelta


from keybert import KeyBERT
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
import vosk
import pyaudio
import json
import threading

kw_extractor = KeyBERT()
nlp = spacy.load("en_core_web_sm")
model = vosk.Model("/Users/arjunhooda/Desktop/vosk-model-small-en-us-0.15")
recognizer = vosk.KaldiRecognizer(model, 16000)
mic = pyaudio.PyAudio()
stream = mic.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
stream.start_stream()
is_transcribing = False
stream_lock = threading.Lock()




def transcribe_live_audio():
    global is_transcribing
    is_transcribing = True
    transcribed_text = ""
    update_status("Processing...", "red")

    
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
    update_status("Transcription Complete", "green")

def update_text_box(text):
    text_box.delete("1.0", tk.END)
    text_box.insert(tk.END, text)





def update_status(status, color):
    status_label.config(text=status, fg=color)


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

def summarize_text(text):
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(text)

    topic = ""
    date_time = ""
    tasks = []

    for ent in doc.ents:
        if ent.label_ in ["DATE", "TIME"]:
            date_time = convert_relative_date(ent.text)
        elif ent.label_ == "EVENT":
            topic = ent.text


    
    if not topic:
        topic = "General Event"

    key_sentences = []
    for sent in doc.sents:
        if any(keyword in sent.text.lower() for keyword in ["meeting", "deadline", "review", "presentation", "feedback"]):
            key_sentences.append(sent.text.strip())



    
    key_points = list(set(key_sentences))
    key_points_text = "\n".join(f"• {point}" for point in key_points) if key_points else "No major points detected."


    
    for token in doc:
        if token.pos_ == "VERB":
            task_object = [child.text for child in token.children if child.dep_ in ["dobj", "pobj"]]
            if task_object:
                task_text = f"{token.text} {task_object[0]}"
                task_with_time = f"{task_text} (by {date_time})" if date_time else task_text
                tasks.append(task_with_time)

    task_list = "\n".join(f"• {task}" for task in set(tasks)) if tasks else "No specific tasks detected."

    
    summary_text = (
        f"TOPIC: {topic}\n\n"
        f"DATE AND TIME: {date_time if date_time else 'Not Specified'}\n\n"
        f"KEY POINTS:\n{key_points_text}\n\n"
        f"TO-DO TASKS:\n{task_list}"
    )

    text_box.delete("1.0", tk.END)
    text_box.insert(tk.END, summary_text)




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

def add_event():
    text = text_box.get("1.0", tk.END).strip()
    summarize_text(text)
    summary = text_box.get("1.0", tk.END).strip().split("\n")
    topic = summary[0].replace("TOPIC: ", "")
    date = summary[2].replace("DATE AND TIME: ", "")
    if "Not Specified" not in date:
        add_event_to_calendar(topic, date)
        messagebox.showinfo("Success", "Event added to calendar.")
    else:
        messagebox.showinfo("No Date Found", "Could not add event to calendar.")



def send_email_via_gmail():
    text = text_box.get("1.0", tk.END).strip().split("\n")

    topic = text[0].replace("TOPIC: ", "").strip()
    date = text[2].replace("DATE AND TIME: ", "").strip()

    key_points_index = text.index("KEY POINTS:") + 1 if "KEY POINTS:" in text else None
    todo_index = text.index("TO-DO TASKS:") + 1 if "TO-DO TASKS:" in text else None

    key_points = "\n".join(
        text[key_points_index:todo_index - 1]).strip() if key_points_index and todo_index else "No key points detected."
    todo_tasks = "\n".join(text[todo_index:]).strip() if todo_index else "No tasks found."

    email_body = f"TOPIC: {topic}\n\nDATE AND TIME: {date}\n\nKEY POINTS:\n{key_points}\n\nTO-DO TASKS:\n{todo_tasks}"

    
    recipient = simpledialog.askstring("Input", "Enter recipient email:")


    
    if recipient:
        flow = InstalledAppFlow.from_client_secrets_file(
            "/Users/arjunhooda/Desktop/client_secret_611064723257-mrocll8kheqnmrb09n3p0k7srkfc9bkt.apps.googleusercontent.com.json",
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        creds = flow.run_local_server(port=0)
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(email_body)
        message['subject'] = topic
        message['from'] = 'me'
        message['to'] = recipient

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
        messagebox.showinfo("Success", "Email sent successfully.")

root = tk.Tk()
root.title("Smart Assistant App")
status_label = tk.Label(root, text="Idle", fg="black")
status_label.pack()
text_box = tk.Text(root, height=15, width=60)
text_box.pack()
tk.Button(root, text="Start Transcription", command=start_transcription).pack()
tk.Button(root, text="Stop Transcription", command=stop_transcription).pack(pady=5)
tk.Button(root, text="Summarize Event", command=lambda: summarize_text(text_box.get("1.0", tk.END).strip())).pack()
tk.Button(root, text="Add Event to Calendar", command=add_event).pack()
tk.Button(root, text="Send Summary via Email", command=send_email_via_gmail).pack()
root.mainloop()
