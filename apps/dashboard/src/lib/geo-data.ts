export interface CountryInfo {
  code: string;
  name: string;
  dialCode: string;
  flag: string;
}

export interface OptionItem {
  value: string;
  label: string;
  sublabel?: string;
  badge?: string;
  keywords?: string[];
}

export const COUNTRIES: CountryInfo[] = [
  { code: "US", name: "United States", dialCode: "+1", flag: "🇺🇸" },
  { code: "IN", name: "India", dialCode: "+91", flag: "🇮🇳" },
  { code: "GB", name: "United Kingdom", dialCode: "+44", flag: "🇬🇧" },
  { code: "CA", name: "Canada", dialCode: "+1", flag: "🇨🇦" },
  { code: "AU", name: "Australia", dialCode: "+61", flag: "🇦🇺" },
  { code: "DE", name: "Germany", dialCode: "+49", flag: "🇩🇪" },
  { code: "FR", name: "France", dialCode: "+33", flag: "🇫🇷" },
  { code: "AE", name: "United Arab Emirates", dialCode: "+971", flag: "🇦🇪" },
  { code: "SA", name: "Saudi Arabia", dialCode: "+966", flag: "🇸🇦" },
  { code: "SG", name: "Singapore", dialCode: "+65", flag: "🇸🇬" },
  { code: "JP", name: "Japan", dialCode: "+81", flag: "🇯🇵" },
  { code: "KR", name: "South Korea", dialCode: "+82", flag: "🇰🇷" },
  { code: "CN", name: "China", dialCode: "+86", flag: "🇨🇳" },
  { code: "BR", name: "Brazil", dialCode: "+55", flag: "🇧🇷" },
  { code: "MX", name: "Mexico", dialCode: "+52", flag: "🇲🇽" },
  { code: "ES", name: "Spain", dialCode: "+34", flag: "🇪🇸" },
  { code: "IT", name: "Italy", dialCode: "+39", flag: "🇮🇹" },
  { code: "NL", name: "Netherlands", dialCode: "+31", flag: "🇳🇱" },
  { code: "CH", name: "Switzerland", dialCode: "+41", flag: "🇨🇭" },
  { code: "SE", name: "Sweden", dialCode: "+46", flag: "🇸🇪" },
  { code: "NO", name: "Norway", dialCode: "+47", flag: "🇳🇴" },
  { code: "IE", name: "Ireland", dialCode: "+353", flag: "🇮🇪" },
  { code: "NZ", name: "New Zealand", dialCode: "+64", flag: "🇳🇿" },
  { code: "ZA", name: "South Africa", dialCode: "+27", flag: "🇿🇦" },
  { code: "NG", name: "Nigeria", dialCode: "+234", flag: "🇳🇬" },
  { code: "EG", name: "Egypt", dialCode: "+20", flag: "🇪🇬" },
  { code: "KE", name: "Kenya", dialCode: "+254", flag: "🇰🇪" },
  { code: "ID", name: "Indonesia", dialCode: "+62", flag: "🇮🇩" },
  { code: "MY", name: "Malaysia", dialCode: "+60", flag: "🇲🇾" },
  { code: "TH", name: "Thailand", dialCode: "+66", flag: "🇹🇭" },
  { code: "VN", name: "Vietnam", dialCode: "+84", flag: "🇻🇳" },
  { code: "PH", name: "Philippines", dialCode: "+63", flag: "🇵🇭" },
  { code: "PK", name: "Pakistan", dialCode: "+92", flag: "🇵🇰" },
  { code: "BD", name: "Bangladesh", dialCode: "+880", flag: "🇧🇩" },
  { code: "TR", name: "Turkey", dialCode: "+90", flag: "🇹🇷" },
  { code: "IL", name: "Israel", dialCode: "+972", flag: "🇮🇱" },
  { code: "QA", name: "Qatar", dialCode: "+974", flag: "🇶🇦" },
  { code: "KW", name: "Kuwait", dialCode: "+965", flag: "🇰🇼" },
  { code: "AR", name: "Argentina", dialCode: "+54", flag: "🇦🇷" },
  { code: "CL", name: "Chile", dialCode: "+56", flag: "🇨🇱" },
  { code: "CO", name: "Colombia", dialCode: "+57", flag: "🇨🇴" },
  { code: "PL", name: "Poland", dialCode: "+48", flag: "🇵🇱" },
  { code: "AT", name: "Austria", dialCode: "+43", flag: "🇦🇹" },
  { code: "BE", name: "Belgium", dialCode: "+32", flag: "🇧🇪" },
  { code: "DK", name: "Denmark", dialCode: "+45", flag: "🇩🇰" },
  { code: "FI", name: "Finland", dialCode: "+358", flag: "🇫🇮" },
  { code: "PT", name: "Portugal", dialCode: "+351", flag: "🇵🇹" },
  { code: "GR", name: "Greece", dialCode: "+30", flag: "🇬🇷" },
];

export function detectCountry(phone: string): CountryInfo {
  const cleaned = phone.trim();
  if (!cleaned.startsWith("+")) {
    return COUNTRIES[0]; // Default US
  }

  // Sort by dialCode length descending so +971 is matched before +97, +1 matches after +1xxx
  const sorted = [...COUNTRIES].sort(
    (a, b) => b.dialCode.length - a.dialCode.length
  );
  for (const c of sorted) {
    if (cleaned.startsWith(c.dialCode)) {
      return c;
    }
  }
  return COUNTRIES[0];
}

const PRIORITY_TIMEZONES: OptionItem[] = [
  {
    value: "Asia/Kolkata",
    label: "Asia/Kolkata (India Standard Time)",
    sublabel: "GMT+5:30",
    badge: "🇮🇳",
    keywords: ["india", "kolkata", "calcutta", "delhi", "mumbai", "ist", "bharat", "asia/kolkata"],
  },
  {
    value: "Asia/Calcutta",
    label: "Asia/Calcutta (India Standard Time)",
    sublabel: "GMT+5:30",
    badge: "🇮🇳",
    keywords: ["india", "kolkata", "calcutta", "delhi", "mumbai", "ist", "bharat", "asia/calcutta"],
  },
  {
    value: "UTC",
    label: "UTC (Coordinated Universal Time)",
    sublabel: "GMT+0",
    badge: "🌐",
    keywords: ["utc", "gmt", "zulu", "universal"],
  },
  {
    value: "America/New_York",
    label: "America/New York (US Eastern)",
    sublabel: "GMT-4",
    badge: "🇺🇸",
    keywords: ["us", "usa", "eastern", "est", "edt", "new york", "nyc"],
  },
  {
    value: "America/Chicago",
    label: "America/Chicago (US Central)",
    sublabel: "GMT-5",
    badge: "🇺🇸",
    keywords: ["us", "usa", "central", "cst", "cdt", "chicago"],
  },
  {
    value: "America/Denver",
    label: "America/Denver (US Mountain)",
    sublabel: "GMT-6",
    badge: "🇺🇸",
    keywords: ["us", "usa", "mountain", "mst", "mdt", "denver"],
  },
  {
    value: "America/Los_Angeles",
    label: "America/Los Angeles (US Pacific)",
    sublabel: "GMT-7",
    badge: "🇺🇸",
    keywords: ["us", "usa", "pacific", "pst", "pdt", "los angeles", "sf", "california"],
  },
  {
    value: "Europe/London",
    label: "Europe/London (UK)",
    sublabel: "GMT+1",
    badge: "🇬🇧",
    keywords: ["uk", "london", "britain", "england", "bst", "gmt"],
  },
  {
    value: "Europe/Paris",
    label: "Europe/Paris (Central Europe)",
    sublabel: "GMT+2",
    badge: "🇫🇷",
    keywords: ["france", "paris", "europe", "cet", "cest"],
  },
  {
    value: "Europe/Berlin",
    label: "Europe/Berlin (Germany)",
    sublabel: "GMT+2",
    badge: "🇩🇪",
    keywords: ["germany", "berlin", "europe", "cet", "cest"],
  },
  {
    value: "Asia/Dubai",
    label: "Asia/Dubai (UAE / Gulf)",
    sublabel: "GMT+4",
    badge: "🇦🇪",
    keywords: ["uae", "dubai", "gulf", "gst", "emirates", "abu dhabi"],
  },
  {
    value: "Asia/Singapore",
    label: "Asia/Singapore",
    sublabel: "GMT+8",
    badge: "🇸🇬",
    keywords: ["singapore", "sgt"],
  },
  {
    value: "Asia/Tokyo",
    label: "Asia/Tokyo (Japan)",
    sublabel: "GMT+9",
    badge: "🇯🇵",
    keywords: ["japan", "tokyo", "jst"],
  },
  {
    value: "Australia/Sydney",
    label: "Australia/Sydney (AEST)",
    sublabel: "GMT+10",
    badge: "🇦🇺",
    keywords: ["australia", "sydney", "aest", "aedt", "melbourne"],
  },
];

let cachedTimezones: OptionItem[] | null = null;

export function getTimezones(): OptionItem[] {
  if (cachedTimezones) {
    return cachedTimezones;
  }

  const prioritySet = new Set(PRIORITY_TIMEZONES.map((p) => p.value));
  const otherZones: OptionItem[] = [];

  try {
    const rawZones = Intl.supportedValuesOf("timeZone");
    const now = new Date();
    for (const tz of rawZones) {
      if (prioritySet.has(tz)) continue;

      let offset = "";
      try {
        const parts = new Intl.DateTimeFormat("en", {
          timeZone: tz,
          timeZoneName: "shortOffset",
        }).formatToParts(now);
        offset = parts.find((p) => p.type === "timeZoneName")?.value || "";
      } catch {
        offset = "";
      }

      otherZones.push({
        value: tz,
        label: tz.replace(/_/g, " "),
        sublabel: offset,
      });
    }
  } catch {
    // Priority list handles fallback
  }

  cachedTimezones = [...PRIORITY_TIMEZONES, ...otherZones];
  return cachedTimezones;
}

export const LANGUAGES: OptionItem[] = [
  { value: "en-US", label: "English (US)", sublabel: "en-US" },
  { value: "en-IN", label: "English (India)", sublabel: "en-IN" },
  { value: "en-GB", label: "English (UK)", sublabel: "en-GB" },
  { value: "hi-IN", label: "Hindi (हिन्दी)", sublabel: "hi-IN" },
  { value: "es-ES", label: "Spanish (Spain)", sublabel: "es-ES" },
  { value: "es-MX", label: "Spanish (Mexico)", sublabel: "es-MX" },
  { value: "fr-FR", label: "French (Français)", sublabel: "fr-FR" },
  { value: "de-DE", label: "German (Deutsch)", sublabel: "de-DE" },
  { value: "pt-BR", label: "Portuguese (Brasil)", sublabel: "pt-BR" },
  { value: "it-IT", label: "Italian (Italiano)", sublabel: "it-IT" },
  { value: "ja-JP", label: "Japanese (日本語)", sublabel: "ja-JP" },
  { value: "zh-CN", label: "Chinese (Simplified)", sublabel: "zh-CN" },
  { value: "ar-SA", label: "Arabic (العربية)", sublabel: "ar-SA" },
  { value: "ru-RU", label: "Russian (Русский)", sublabel: "ru-RU" },
  { value: "ko-KR", label: "Korean (한국어)", sublabel: "ko-KR" },
  { value: "id-ID", label: "Indonesian (Bahasa)", sublabel: "id-ID" },
  { value: "nl-NL", label: "Dutch (Nederlands)", sublabel: "nl-NL" },
  { value: "tr-TR", label: "Turkish (Türkçe)", sublabel: "tr-TR" },
  { value: "vi-VN", label: "Vietnamese (Tiếng Việt)", sublabel: "vi-VN" },
  { value: "th-TH", label: "Thai (ไทย)", sublabel: "th-TH" },
  { value: "mr-IN", label: "Marathi (मराठी)", sublabel: "mr-IN" },
  { value: "bn-IN", label: "Bengali (বাংলা)", sublabel: "bn-IN" },
  { value: "te-IN", label: "Telugu (తెలుగు)", sublabel: "te-IN" },
  { value: "ta-IN", label: "Tamil (தமிழ்)", sublabel: "ta-IN" },
  { value: "gu-IN", label: "Gujarati (ગુજરાતી)", sublabel: "gu-IN" },
  { value: "kn-IN", label: "Kannada (ಕನ್ನಡ)", sublabel: "kn-IN" },
  { value: "ml-IN", label: "Malayalam (മലയാളം)", sublabel: "ml-IN" },
  { value: "pa-IN", label: "Punjabi (ਪੰਜਾਬੀ)", sublabel: "pa-IN" },
];
