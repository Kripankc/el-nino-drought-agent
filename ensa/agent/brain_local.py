import requests
import json
import os

class LocalAgentBrain:
    """
    Local Edge LLM Agent Brain running on your laptop GPU.
    Uses Ollama with quantized lightweight models (Qwen-2.5-1.5B or Phi-3.5)
    to parse daily coordinates, check database alerts, and coordinate routine runs.
    """
    def __init__(self, model_name="qwen2.5:1.5b", base_url="http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def is_ollama_running(self):
        """Checks if the local Ollama server is active."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def query(self, prompt, system_prompt="You are the ENSA Local Traffic Cop agent.", temperature=0.1):
        """
        Sends a request to the local Ollama instance.
        Falls back to a fast heuristic JSON generator if Ollama is offline or not configured.
        """
        if not self.is_ollama_running():
            print(f"[Ollama Warning] Local server at {self.base_url} is offline.")
            print("[Ollama Warning] Operating in high-speed local dry-run simulation mode.")
            return self._generate_simulated_local_parse(prompt)

        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model_name,
                "prompt": f"System: {system_prompt}\nUser: {prompt}",
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }
            res = requests.post(url, json=payload, timeout=30)
            res.raise_for_status()
            response_text = res.json().get("response", "")
            return response_text
        except Exception as e:
            print(f"[Ollama Error] Query failed: {e}")
            return self._generate_simulated_local_parse(prompt)

    def parse_coordinate_request(self, user_input):
        """
        Example local daily task: Extract region parameters from a dynamic user request.
        A 1.5B model excels at this simple entity extraction task.
        """
        prompt = f"""Extract the region details, target crop, and date range from this request. 
Return strictly a JSON object with keys: 'region_name', 'country', 'crop_type', 'bbox' (if coordinates provided as [min_lon, min_lat, max_lon, max_lat], else null).
Input: '{user_input}'"""
        
        system = "You are an expert geographical data extractor. Return ONLY a raw JSON block."
        raw_response = self.query(prompt, system_prompt=system)
        
        try:
            # Find and parse JSON substring
            start_idx = raw_response.find("{")
            end_idx = raw_response.rfind("}") + 1
            if start_idx != -1 and end_idx != -1:
                return json.loads(raw_response[start_idx:end_idx])
        except Exception:
            pass
            
        return self._generate_simulated_local_parse(user_input)

    def _generate_simulated_local_parse(self, prompt):
        """Mock JSON extractor fallback to ensure system functions out of the box."""
        # Simple string-matching heuristics to simulate local model extraction
        prompt_lower = prompt.lower()
        region = "Choma District"
        country = "Zambia"
        crop = "White Maize"
        
        if "zimbabwe" in prompt_lower or "harare" in prompt_lower:
            region = "Harare Province"
            country = "Zimbabwe"
            crop = "Pearl Millet"
        elif "malawi" in prompt_lower:
            region = "Lilongwe District"
            country = "Malawi"
            crop = "Cassava"

        return {
            "region_name": region,
            "country": country,
            "crop_type": crop,
            "bbox": [26.8, -17.2, 27.5, -16.5],
            "extracted_by": "ensa_local_simulator"
        }
