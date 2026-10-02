"""Credential-free Gnani catalog, sourced from docs/providers/gnani."""

GNANI_LANGUAGES = (
    "en-IN",
    "hi-IN",
    "ta-IN",
    "te-IN",
    "kn-IN",
    "ml-IN",
    "mr-IN",
    "bn-IN",
    "gu-IN",
    "pa-IN",
)
GNANI_VOICES_BY_LANGUAGE = {
    "en-IN": ("Pranav", "Kaveri", "Trupti", "Devika", "Shlok", "Girish"),
    "hi-IN": (
        "Nalini",
        "Bhavna",
        "Yashvi",
        "Urmila",
        "Jwala",
        "Chitra",
        "Ambuja",
        "Deepak",
        "Roopesh",
        "Vikrant",
        "Hemraj",
        "Jalaj",
        "Omkar",
    ),
    "ta-IN": ("Asmita", "Trisha", "Brinda", "Vedika", "Noopur"),
    "te-IN": ("Suhana", "Lehara", "Lavanya", "Yukti", "Varuni"),
    "kn-IN": ("Saanvi", "Kavin"),
    "ml-IN": ("Reshma", "Riyaan"),
    "mr-IN": ("Zahira", "Ishaan"),
    "bn-IN": ("Kirra", "Dhruva"),
    "gu-IN": ("Falak", "Veera"),
    "pa-IN": ("Mehuli", "Zayan"),
    "auto": ("Poorvi",),
}
GNANI_VOICES = tuple(voice for voices in GNANI_VOICES_BY_LANGUAGE.values() for voice in voices)
