import os
import requests
import json
from ensa.config import OPENAI_API_KEY, ANTHROPIC_API_KEY, BASE_DIR

class CloudAgentBrain:
    """
    Cloud Cognitive Core for ENSA.
    Handles the computationally and reasoning-heavy tasks (once/twice a day)
    such as multi-event calibration reflections and dynamic parameter adjustments.
    """
    def __init__(self, gemini_api_key=None, provider="gemini"):
        self.provider = provider
        self.api_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or OPENAI_API_KEY

    def query_gemini_flash(self, system_instruction, prompt_content):
        """
        Queries Gemini 1.5 Flash using its 100% free developer tier API.
        Does not stress your local GPU.
        """
        if not self.api_key:
            print("[Cloud Warning] No Gemini API key detected. Operating in simulated cloud reasoning mode.")
            return self._generate_simulated_cloud_reflection(prompt_content)

        try:
            # We use standard HTTP requests to ensure compatibility with all setups and zero environment overhead
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt_content}]}],
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.2
                }
            }
            res = requests.post(url, headers=headers, json=payload, timeout=45)
            res.raise_for_status()
            
            # Extract response text
            candidates = res.json().get("candidates", [])
            if candidates:
                text_out = candidates[0]["content"]["parts"][0]["text"]
                return json.loads(text_out)
        except Exception as e:
            print(f"[Cloud API Error] Gemini call failed: {e}")
            
        return self._generate_simulated_cloud_reflection(prompt_content)

    def run_daily_calibration(self, batch_anomalies):
        """
        Runs the multi-event calibration and biophysical gap analysis.
        Ingests the rolling 2-3 week forecasting gaps and outputs revised threshold weights.
        """
        system = """You are the ENSA Biophysical Calibration Supervisor. 
You analyze prediction gaps (global forecasts vs ground satellite truth) over multiple historical droughts (2015, 2018, 2023).
You return a JSON dictionary with keys: 'adjusted_weights' (dict with precipitation, vegetation, soil_moisture), 'calibration_rationale' (str), and 'estimated_pdsi_dampener' (float)."""

        prompt = f"""Review these active target anomalies and prediction gaps for this week:
{json.dumps(batch_anomalies, indent=2)}

Analyze the historical discrepancies and soil retention. Output the calibrated dynamic weights and Palmer PDSI dampeners."""

        return self.query_gemini_flash(system, prompt)

    def _generate_simulated_cloud_reflection(self, prompt_content):
        """Mock high-fidelity cloud reasoning outputs when offline or no API keys exist."""
        return {
            "adjusted_weights": {
                "precipitation": 0.35,
                "vegetation": 0.25,
                "soil_moisture": 0.40
            },
            "calibration_rationale": "Simulated Cloud reflection: Confirmed active soil water retention. The historical multi-event calibration (2015, 2018, 2023) indicates ECMWF overpredicts rapid desiccation by 15% during early-season El Niño phases due to sub-canopy humidity. Adjusting soil moisture weight upwards.",
            "estimated_pdsi_dampener": 0.88,
            "simulated": True
        }
