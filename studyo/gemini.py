"""Gemini ile kurgu plani (yalnizca metin). Anahtar ayarlar.json'dan ya da LunaTranslator'dan okunur."""
import json
import time

import requests

from . import ayar as ayar_modulu


def _gemini(model, anahtar, metin, zaman_asimi):
    r = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model,
        headers={"x-goog-api-key": anahtar},
        json={"contents": [{"role": "user", "parts": [{"text": metin}]}],
              "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}},
        timeout=zaman_asimi,
    )
    if r.status_code != 200:
        raise RuntimeError("HTTP %d" % r.status_code)
    cevap = r.json()
    return json.loads("".join(p.get("text", "") for p in cevap["candidates"][0]["content"]["parts"]))


def iste(metin, ayar, gunluk=print):
    anahtar = ayar_modulu.gemini_anahtari(ayar)
    if not anahtar:
        gunluk("  Gemini anahtari yok, atlaniyor")
        return None
    modeller = ayar["gemini_modelleri"]
    for sira, model in enumerate(modeller):
        son_model = sira == len(modeller) - 1
        # Guclu model sik sik mesgul (503 / cevapsiz): bir kez dene, sonrakine gec.
        # Son model: acele yok (video isi), artan beklemeyle birkac kez dene.
        bekleme = [10, 30, 60] if son_model else []
        for deneme in range(len(bekleme) + 1):
            try:
                ham = _gemini(model, anahtar, metin, 120 if son_model else 60)
                gunluk("  Gemini plani: %s" % model)
                return ham
            except Exception as e:
                gunluk("  %s olmadi (%s)" % (model, str(e)[:120]))
                if deneme < len(bekleme):
                    time.sleep(bekleme[deneme])
    return None
