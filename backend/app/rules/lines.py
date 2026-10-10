"""Approved spoken lines. The bot speaks these verbatim when a tool returns `say`.

- No line contains a number about money. tests/test_price_guard.py checks every line in
  every language with contains_price().
- English and Hindi only (Marathi dropped by decision, 2026-10-10: a Marathi-preferring caller is
  answered in Hindi/English and offered a human callback). Hindi is Devanagari for TTS, female
  voice persona (verb forms like "रही हूँ" assume it). Machine-quality: get a native speaker to review.
- price.deflect (en) is pricing.md's "only acceptable response", verbatim.
"""
from .price_guard import contains_price

LANGS = ("en", "hi")

LINES: dict[str, dict[str, str]] = {
    # ---- ASK: one direct question (qualified.md "At the boundary") ----
    "ask.scope": {
        "en": "Just so I point you to the right person: are you looking for a complete redesign with execution, where we handle the design, materials and the work on site, or mainly ideas and advice?",
        "hi": "सही व्यक्ति तक पहुँचाने के लिए एक बात बताइए: क्या आप डिज़ाइन से लेकर काम पूरा होने तक पूरा रीडिज़ाइन चाहते हैं, या सिर्फ़ कुछ सुझाव और सलाह?",
    },
    "ask.area": {
        "en": "Which area of Pune is the site in?",
        "hi": "आपकी साइट पुणे के किस इलाके में है?",
    },
    "ask.area_india": {
        "en": "Which city, and which area of it, is the site in?",
        "hi": "आपकी साइट किस शहर में और उसके किस इलाके में है?",
    },
    "ask.area_unknown": {
        "en": "Is that within Pune city or Pimpri-Chinchwad?",
        "hi": "क्या यह पुणे शहर या पिंपरी-चिंचवड के अंदर आता है?",
    },
    "ask.deadline": {  # Nikhil's own question, qualified.md criterion 3
        "en": "When would you need the project complete?",
        "hi": "आपको प्रोजेक्ट कब तक पूरा चाहिए?",
    },
    "ask.deadline_exact": {
        "en": "Could you give me the date you'd need it finished by? An approximate date is fine.",
        "hi": "क्या आप बता सकते हैं कि किस तारीख़ तक काम पूरा होना चाहिए? अंदाज़न तारीख़ भी चलेगी।",
    },
    "ask.deadline_flexible": {
        "en": "Is that date fixed, or could the project finish a little later than that?",
        "hi": "क्या वह तारीख़ पक्की है, या काम थोड़ा बाद में भी पूरा हो सकता है?",
    },
    # ---- QUALIFIED ----
    "qualified": {
        "en": "Thank you, this sounds like exactly the kind of project our designers love to work on. Let me find a consultation slot for you; it's free and there's no obligation.",
        "hi": "धन्यवाद, यह बिल्कुल वैसा प्रोजेक्ट है जिस पर हमारे डिज़ाइनर काम करना पसंद करते हैं। मैं आपके लिए कंसल्टेशन का समय देखती हूँ; यह मुफ़्त है और कोई बाध्यता नहीं है।",
    },
    # ---- NURTURE ----
    "nurture.timeline": {
        "en": "I want to be honest with you: a redesign with full execution needs at least two to three months, so we couldn't do it justice by that date. If a later finish works for you, we'd love to help. Shall I have a designer call you to plan it from there?",
        "hi": "मैं आपसे ईमानदारी से कहूँ तो पूरे काम के साथ रीडिज़ाइन में कम से कम दो-तीन महीने लगते हैं, इसलिए उस तारीख़ तक हम अच्छा काम नहीं कर पाएँगे। अगर थोड़ा बाद में पूरा होना ठीक है, तो हमें मदद करके ख़ुशी होगी। क्या मैं किसी डिज़ाइनर से आपको कॉल करवाऊँ?",
    },
    # ---- DECLINE ----
    "decline.timeline_fixed": {
        "en": "I want to be honest: a redesign with full execution takes at least two to three months, so we couldn't do it well in that time, and I wouldn't want to promise something we can't deliver. If your timeline changes, please do call us again.",
        "hi": "ईमानदारी से कहूँ तो पूरे काम के साथ रीडिज़ाइन में कम से कम दो-तीन महीने लगते हैं, इसलिए इतने समय में हम इसे अच्छे से नहीं कर पाएँगे, और मैं ऐसा वादा नहीं करना चाहती जो हम निभा न सकें। अगर आपकी टाइमलाइन बदले, तो ज़रूर दोबारा कॉल कीजिए।",
    },
    "decline.area_india": {
        "en": "Thank you so much for thinking of us. We take on projects anywhere in India, but not outside it, because our execution depends on our own contractors being on site, so I'm sorry we can't help with this one.",
        "hi": "हमें याद करने के लिए बहुत धन्यवाद। हम पूरे भारत में प्रोजेक्ट लेते हैं, पर भारत के बाहर नहीं, क्योंकि हमारा काम हमारे अपने कॉन्ट्रैक्टर्स साइट पर करते हैं। माफ़ कीजिए, इस बार हम मदद नहीं कर पाएँगे।",
    },
    "decline.area": {
        "en": "Thank you so much for thinking of us. We only take on projects in Pune city and Pimpri-Chinchwad, because our execution depends on our own contractors being on site, so I'm sorry we can't help with this one.",
        "hi": "हमें याद करने के लिए बहुत धन्यवाद। हम सिर्फ़ पुणे शहर और पिंपरी-चिंचवड में प्रोजेक्ट लेते हैं, क्योंकि हमारा काम हमारे अपने कॉन्ट्रैक्टर्स साइट पर करते हैं। माफ़ कीजिए, इस बार हम मदद नहीं कर पाएँगे।",
    },
    "decline.excluded_category": {
        "en": "Thank you for reaching out. We focus on homes, offices, clinics and studios. Restaurants, hotels, shops and gyms need a specialist studio with different compliance experience, so we wouldn't be the right fit.",
        "hi": "संपर्क करने के लिए धन्यवाद। हम घर, ऑफ़िस, क्लिनिक और स्टूडियो पर काम करते हैं। रेस्टोरेंट, होटल, दुकान और जिम के लिए अलग विशेषज्ञ स्टूडियो की ज़रूरत होती है, इसलिए हम सही विकल्प नहीं होंगे।",
    },
    "decline.advice_only": {
        "en": "We're a full-service studio, so our projects always include design and execution together; we don't do advice-only or styling visits. If you decide to go ahead with a complete redesign, we'd love to hear from you.",
        "hi": "हम फ़ुल-सर्विस स्टूडियो हैं, इसलिए हमारे हर प्रोजेक्ट में डिज़ाइन और काम दोनों साथ होते हैं; सिर्फ़ सलाह या स्टाइलिंग के लिए हम विज़िट नहीं करते। अगर आप पूरा रीडिज़ाइन करवाने का फ़ैसला करें, तो हमें ज़रूर बताइए।",
    },
    "decline.furniture_only": {
        "en": "We only source furniture as part of a full design project, so we wouldn't be the right fit for furniture alone. If you plan a room redesign later, do call us.",
        "hi": "हम फ़र्नीचर सिर्फ़ पूरे डिज़ाइन प्रोजेक्ट के हिस्से के रूप में ही सोर्स करते हैं, इसलिए सिर्फ़ फ़र्नीचर के लिए हम सही विकल्प नहीं होंगे। आगे कभी कमरे का रीडिज़ाइन करें तो ज़रूर कॉल कीजिए।",
    },
    "decline.vastu_only": {
        "en": "We include Vastu in all our designs, but we don't offer standalone Vastu consultations. If you plan a redesign, we'd be happy to help then.",
        "hi": "हम अपने सभी डिज़ाइन में वास्तु का ध्यान रखते हैं, लेकिन अलग से वास्तु सलाह नहीं देते। अगर आप रीडिज़ाइन करवाएँ, तो हमें मदद करके ख़ुशी होगी।",
    },
    "decline.architecture": {
        "en": "We're interior designers rather than architects, so we don't move walls or take on structural work. For that you'd need an architect; once the structure is settled, we'd be glad to design the interiors.",
        "hi": "हम इंटीरियर डिज़ाइनर हैं, आर्किटेक्ट नहीं, इसलिए दीवारें हटाने या स्ट्रक्चरल काम हम नहीं करते। उसके लिए आपको आर्किटेक्ट की ज़रूरत होगी; स्ट्रक्चर तय हो जाने के बाद हम इंटीरियर ख़ुशी से डिज़ाइन करेंगे।",
    },
    "decline.commercial_small": {
        "en": "For a space that size, our design and execution team isn't the right scale; we couldn't deliver it at the quality we'd want to promise. A designer who specialises in smaller commercial spaces would serve you better.",
        "hi": "इतनी छोटी जगह के लिए हमारी डिज़ाइन और एग्ज़िक्यूशन टीम सही स्केल पर नहीं है; हम उस क्वालिटी पर काम नहीं कर पाएँगे जिसका हम वादा करते हैं। छोटे कमर्शियल स्पेस में माहिर डिज़ाइनर आपके लिए बेहतर रहेंगे।",
    },
    "decline.commercial_large": {
        "en": "Our commercial work is limited to smaller offices, clinics and studios, so a space this large is beyond what we can take on well right now.",
        "hi": "हमारा कमर्शियल काम छोटे ऑफ़िस, क्लिनिक और स्टूडियो तक सीमित है, इसलिए इतनी बड़ी जगह अभी हम अच्छे से नहीं ले पाएँगे।",
    },
    "decline.budget": {  # T10, without any number
        "en": "Thank you for being so open about the budget. I'll be honest: for the scope you've described, with full execution, that would be well below what a project like this costs with us, and I wouldn't want to bring you to a consultation where it doesn't work for you. A local contractor who works at that level may be a better fit.",
        "hi": "बजट के बारे में खुलकर बताने के लिए धन्यवाद। ईमानदारी से कहूँ तो आपने जो काम बताया है, पूरे एग्ज़िक्यूशन के साथ, उसके लिए यह हमारे यहाँ लगने वाले ख़र्च से काफ़ी कम होगा, और मैं आपको ऐसे कंसल्टेशन पर नहीं बुलाना चाहती जहाँ बात न बने। उस स्तर पर काम करने वाला कोई स्थानीय कॉन्ट्रैक्टर आपके लिए बेहतर रहेगा।",
    },
    "decline.decision_maker": {
        "en": "It sounds like the decision sits with someone else for now. When they're ready to go ahead, they're very welcome to call us directly, and we'll set up a consultation.",
        "hi": "लगता है अभी फ़ैसला किसी और के हाथ में है। जब वे आगे बढ़ना चाहें, तो वे हमें सीधे कॉल कर सकते हैं, और हम कंसल्टेशन तय कर देंगे।",
    },
    "decline.multiple": {  # qualified.md, verbatim
        "en": "This sounds like it may not be the right fit for us right now, but feel free to reach out if your timeline or scope changes.",
        "hi": "लगता है अभी यह प्रोजेक्ट हमारे लिए सही मेल नहीं है, लेकिन अगर आपकी टाइमलाइन या काम का दायरा बदले, तो बेझिझक हमसे संपर्क कीजिए।",
    },
    # ---- ESCALATE ----
    "escalate.complaint": {
        "en": "I'm really sorry, that's not the experience we want for you. I'm sending this to our studio head right now, marked urgent, and a senior person will call you back shortly.",
        "hi": "मुझे सच में खेद है, हम नहीं चाहते कि आपको ऐसा अनुभव हो। मैं इसे अभी हमारे स्टूडियो हेड को अर्जेंट के तौर पर भेज रही हूँ, और कोई सीनियर व्यक्ति जल्द ही आपको कॉल करेंगे।",
    },
    "escalate.existing": {
        "en": "Thank you. I'm passing this straight to your project team, and someone who knows your project will call you back.",
        "hi": "धन्यवाद। मैं यह सीधे आपकी प्रोजेक्ट टीम को भेज रही हूँ, और आपके प्रोजेक्ट को जानने वाला कोई व्यक्ति आपको वापस कॉल करेगा।",
    },
    # ---- Always-available lines ----
    "price.deflect": {  # pricing.md, verbatim
        "en": "Pricing depends on the site, the materials you choose, and the scope; your designer will walk you through it in detail at the consultation. I can book that for you right now if you'd like.",
        "hi": "कीमत साइट, आपके चुने हुए मटीरियल और काम के दायरे पर निर्भर करती है; आपके डिज़ाइनर कंसल्टेशन में आपको सब विस्तार से समझाएँगे। अगर आप चाहें तो मैं अभी वह बुक कर सकती हूँ।",
    },
    "fallback.callback": {  # every tool failure path ends here
        "en": "I'm sorry, I'm having a little trouble with that right now. A person from our studio will call you back on this number.",
        "hi": "माफ़ कीजिए, अभी इसमें थोड़ी दिक़्क़त आ रही है। हमारे स्टूडियो से कोई व्यक्ति आपको इसी नंबर पर वापस कॉल करेगा।",
    },
    "fallback.callback_morning": {
        "en": "A person from our studio will call you back on this number tomorrow morning.",
        "hi": "हमारे स्टूडियो से कोई व्यक्ति आपको कल सुबह इसी नंबर पर वापस कॉल करेगा।",
    },
    "robot.disclosure": {
        "en": "Yes, I'm Aangan Studio's AI assistant. I can answer your questions and book a consultation with one of our designers, or arrange for a person to call you back, whichever you prefer.",
        "hi": "जी हाँ, मैं आंगन स्टूडियो की AI असिस्टेंट हूँ। मैं आपके सवालों के जवाब दे सकती हूँ और हमारे डिज़ाइनर के साथ कंसल्टेशन बुक कर सकती हूँ, या किसी व्यक्ति से आपको कॉल करवा सकती हूँ, जैसा आप चाहें।",
    },
    "human.request": {
        "en": "Of course. Someone from our studio will call you back on this number.",
        "hi": "ज़रूर। हमारे स्टूडियो से कोई व्यक्ति आपको इसी नंबर पर वापस कॉल करेगा।",
    },
    "flag.unresolved": {
        "en": "No problem, I'll note that and your designer will go over it with you.",
        "hi": "कोई बात नहीं, मैं यह नोट कर लेती हूँ, आपके डिज़ाइनर आपसे इस पर बात कर लेंगे।",
    },
    "apology.missed_followup": {  # T16
        "en": "I'm so sorry nobody got back to you; that shouldn't have happened. I'm noting everything now and sending it on as a priority.",
        "hi": "मुझे बहुत खेद है कि आपको कोई जवाब नहीं मिला; ऐसा नहीं होना चाहिए था। मैं अभी सब नोट कर रही हूँ और इसे प्राथमिकता से आगे भेजूँगी।",
    },
    "booking.confirmed": {
        "en": "You're booked for {slot}. Your designer will have everything we've discussed, so you won't need to repeat yourself.",
        "hi": "आपका कंसल्टेशन {slot} के लिए बुक हो गया है। हमने जो भी बात की है, वह सब आपके डिज़ाइनर के पास होगा, ताकि आपको कुछ दोहराना न पड़े।",
    },
    "booking.slots": {
        "en": "I have {slots}. Which works best for you?",
        "hi": "मेरे पास {slots} उपलब्ध हैं। आपके लिए कौन-सा समय सही रहेगा?",
    },
    "booking.failed": {
        "en": "I'm sorry, I couldn't confirm a slot just now. A person from our studio will call you back to fix a time.",
        "hi": "माफ़ कीजिए, मैं अभी स्लॉट पक्का नहीं कर पाई। हमारे स्टूडियो से कोई व्यक्ति समय तय करने के लिए आपको वापस कॉल करेगा।",
    },
}

SAFE_KEY = "fallback.callback"


def normalise_lang(lang: str | None) -> str:
    l = (lang or "en").strip().lower()[:2]
    # Marathi callers get Hindi (closest supported); anything unknown gets English.
    return {"hn": "hi", "mr": "hi", "ma": "hi"}.get(l, l) if l in LANGS or l in ("hn", "mr", "ma") else "en"


def say(key: str, lang: str | None = "en", **fmt) -> str:
    """Return an approved line. If formatting injects anything price-like, return the safe line."""
    lang = normalise_lang(lang)
    entry = LINES.get(key) or LINES[SAFE_KEY]
    text = entry.get(lang) or entry["en"]
    if fmt:
        text = text.format(**fmt)
    if contains_price(text):
        return LINES[SAFE_KEY][lang]
    return text
