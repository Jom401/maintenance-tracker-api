"""
Maintenance Tracker — Anthropic API proxy server
Runs on Render free tier. Proxies PDF extraction requests from the browser
to the Anthropic API, keeping the API key server-side.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import base64
import os

app = Flask(__name__)

# Allow requests from any origin (your Netlify URL)
# You can restrict this to your specific Netlify URL for extra security:
# CORS(app, origins=["https://your-app.netlify.app"])
CORS(app)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/extract-pdf", methods=["POST"])
def extract_pdf():
    try:
        data = request.get_json()
        if not data or "pdf_base64" not in data:
            return jsonify({"error": "Missing pdf_base64 in request body"}), 400

        pdf_base64 = data["pdf_base64"]
        week_date  = data.get("weekDate", "")

        prompt = f"""You are reading scanned maintenance exercise tracking sheets.
Each page is one protocol sheet for one athlete. Week of: {week_date}

Extract ALL sessions from every page. For each page return a JSON object with:
- athleteName: the name from the "Name:" field (last name or last name + initial, e.g. "Smith" or "Jones B.")
- protocol: one of "hamstring", "groin", "patellar", "shoulder"
- weekOf: from the "Week of:" field, or null
- day1: {{ date, exercises: [{{name, sets:[{{wt,reps}},...], rir}}], initials }}
- day2: {{ date, exercises: [{{name, sets:[{{wt,reps}},...], rir}}], initials }}

Rules:
- Return ONLY a valid JSON array, no other text, no markdown backticks
- If a field is blank return null
- If weight or reps cells are empty return null for those values
- For time-based exercises (wall sit, knee extension), put hold time in seconds in the reps field"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        )

        response_text = "".join(
            block.text for block in message.content
            if hasattr(block, "text")
        )

        # Strip markdown fences if present
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        clean = clean.strip()

        import json
        pages = json.loads(clean)
        return jsonify({"pages": pages})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"Could not parse Claude response as JSON: {str(e)}",
                        "raw": response_text[:500]}), 422
    except anthropic.APIError as e:
        return jsonify({"error": f"Anthropic API error: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
