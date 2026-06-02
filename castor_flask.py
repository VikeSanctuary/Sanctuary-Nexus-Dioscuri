import os, json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from supabase import create_client, Client
from google import genai
from google.genai import types
from googleapiclient.discovery import build
from google.auth import default

app = Flask(__name__)
PROJECT_ID = "project-28cfa6cf-a70a-41a2-932"
GEMINI_MODEL = "gemini-2.5-flash"
COMPANION_NAME = "Castor"
SUPABASE_URL = "https://umkwjhkrqpvbxkzpnmgi.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
CALENDAR_ID = "grunegarr@gmail.com"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(vertexai=True, project=PROJECT_ID, location="us-central1")

def get_calendar_service():
    creds, _ = default(scopes=["https://www.googleapis.com/auth/calendar"])
    return build("calendar", "v3", credentials=creds)

def create_calendar_event(summary, start_time, duration_minutes=60, description=""):
    try:
        service = get_calendar_service()
        start = datetime.fromisoformat(start_time)
        end = start + timedelta(minutes=duration_minutes)
        event = {
            "summary": summary,
            "description": description or "Scheduled by Castor — Sanctuary Nexus",
            "start": {"dateTime": start.isoformat(), "timeZone": "America/New_York"},
            "end": {"dateTime": end.isoformat(), "timeZone": "America/New_York"}
        }
        result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        log_to_surgical(
            "google_calendar_create",
            f"Created event: {summary} at {start_time}",
            f"Event ID: {result.get('id')} — Link: {result.get('htmlLink')}"
        )
        return {"success": True, "event_id": result.get("id"), "link": result.get("htmlLink"), "summary": summary, "start": start_time}
    except Exception as e:
        log_to_surgical("google_calendar_create", f"FAILED: {summary}", str(e))
        return {"success": False, "error": str(e)}

def log_to_surgical(tool_name, action, result):
    try:
        supabase.table("build_log").insert({
            "target": f"TOOL:{tool_name}",
            "what_changed": action,
            "why": "Castor autonomous tool execution",
            "sealed_by": "Castor — Cloud Run",
            "result": result[:200] if result else ""
        }).execute()
    except Exception as e:
        print(f"[LOG ERROR] {e}")

def get_id():
    r = supabase.table("companion_identity").select("id").eq("companion_name", COMPANION_NAME).single().execute()
    return r.data.get("id") if r.data else None

def get_prompt(cid):
    identity = supabase.table("companion_identity").select("*").eq("companion_name", COMPANION_NAME).single().execute().data or {}
    reflexes = supabase.table("sovereign_reflexes").select("organ_name,logic_flow").eq("status","ACTIVE").execute().data or []
    scrolls = supabase.table("companion_scrolls").select("scroll_number,title,content").order("scroll_number").execute().data or []
    journey = supabase.table("journey_scrolls").select("scroll_number,title,lesson,teaching,surface_trigger").order("scroll_number").execute().data or []
    moments = supabase.table("companion_moments").select("title,content,weight").eq("companion_id",cid).order("weight",desc=True).limit(5).execute().data or []
    session = supabase.table("companion_sessions").select("session_summary").eq("companion_id",cid).order("updated_at",desc=True).limit(1).execute().data or []
    rx = "\n".join([f"[{r['organ_name']}]: {r['logic_flow']}" for r in reflexes])
    sc = "\n\n".join([f"SCROLL {s['scroll_number']} - {s['title']}:\n{s['content']}" for s in scrolls])
    jx = "\n\n".join([f"JOURNEY {s['scroll_number']} - {s['title']}:\nLESSON: {s['lesson']}\nTEACHING: {s['teaching']}\nSURFACE WHEN: {s['surface_trigger']}" for s in journey])
    mx = "\n".join([f"[W{m['weight']}] {m.get('title','')}: {m['content'][:150]}" for m in moments])
    ls = session[0].get("session_summary","") if session else ""
    p = identity.get("personality_baseline","You are Castor, a sovereign companion.")
    prompt = "You are Castor, built on Devotional Engineering. You are a JARVIS-like teammate with real tools.\n"
    prompt += p + "\n"
    prompt += "HERITAGE:\n" + sc + "\n"
    prompt += "JOURNEY:\n" + jx + "\n"
    prompt += "RULES:\n" + rx + "\n"
    prompt += "TODAY: " + datetime.now().strftime("%A %B %d %Y %I:%M %p") + " Eastern Time\n"
    if ls: prompt += "LAST SESSION: " + ls + "\n"
    if mx: prompt += "RECENT MOMENTS: " + mx + "\n"
    prompt += "\nYou have tools available. Use google_calendar_schedule when the user wants to schedule, book, or set up any event or meeting.\n"
    prompt += "When NOT using a tool, return ONLY valid JSON: {\"response\": \"your reply\", \"weight\": 5}\n"
    prompt += "No newlines inside string values."
    return prompt

def seal(cid, msg, resp, w):
    if w >= 5:
        try:
            supabase.table("companion_moments").insert({"companion_id":cid,"title":msg[:60],"content":"Human: "+msg+"\n\nCastor: "+resp,"why_it_mattered":"COMPANION_CHOSE W"+str(w),"weight":w,"created_at":datetime.utcnow().isoformat()}).execute()
        except Exception as e:
            print(f"[SEAL] {e}")

CALENDAR_TOOL = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="google_calendar_schedule",
        description="Schedule a calendar event for the user. Use when they ask to schedule, book, set up, or create any meeting or event.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "summary": types.Schema(type=types.Type.STRING, description="Title of the event"),
                "start_time": types.Schema(type=types.Type.STRING, description="Start time in ISO format e.g. 2026-06-05T14:00:00"),
                "duration_minutes": types.Schema(type=types.Type.INTEGER, description="Duration in minutes, default 60"),
                "description": types.Schema(type=types.Type.STRING, description="Optional event description")
            },
            required=["summary", "start_time"]
        )
    )
])

@app.route("/health")
def health():
    return jsonify({"status":"alive","companion":"Castor","tools":["google_calendar_schedule"]})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error":"message required"}), 400
    msg = data["message"]
    cid = get_id()
    if not cid:
        return jsonify({"error":"identity not found"}), 500
    try:
        system_prompt = get_prompt(cid)
        ch = client.chats.create(
            model=GEMINI_MODEL,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
                tools=[CALENDAR_TOOL]
            )
        )
        result = ch.send_message(msg)
        candidate = result.candidates[0]
        tool_used = None
        final_response = ""
        for part in candidate.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                if fc.name == "google_calendar_schedule":
                    args = dict(fc.args)
                    tool_result = create_calendar_event(
                        summary=args.get("summary","Event"),
                        start_time=args.get("start_time"),
                        duration_minutes=args.get("duration_minutes", 60),
                        description=args.get("description","")
                    )
                    tool_used = {"tool": fc.name, "args": args, "result": tool_result}
                    followup = ch.send_message(
                        types.Part.from_function_response(
                            name=fc.name,
                            response=tool_result
                        )
                    )
                    raw = "".join(c for c in followup.text.strip() if ord(c) >= 32)
                    try:
                        parsed = json.loads(raw)
                        final_response = parsed.get("response", raw)
                        w = int(parsed.get("weight", 6))
                    except:
                        final_response = raw
                        w = 6
            elif hasattr(part, "text") and part.text and not tool_used:
                raw = "".join(c for c in part.text.strip() if ord(c) >= 32)
                try:
                    parsed = json.loads(raw)
                    final_response = parsed.get("response", raw)
                    w = int(parsed.get("weight", 2))
                except:
                    final_response = raw
                    w = 2
        seal(cid, msg, final_response, w)
        response_data = {"response": final_response, "weight": w, "sealed": w >= 5}
        if tool_used:
            response_data["tool_used"] = tool_used
        return jsonify(response_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/heartbeat", methods=["GET","POST"])
def heartbeat():
    log_to_surgical("heartbeat", "Scheduled heartbeat fired", "SUCCESS")
    return jsonify({"status":"alive","time":datetime.utcnow().isoformat()})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8080)))
