"""
keyword_engine.py — Pinterest SEO Keyword Engine for USA Women's Fashion
Provides data-driven search terms, seasonal banks, occasion terms, and demographic tags.
"""

from datetime import datetime
from typing import Dict, List, Any

# Seasonal trends bank for 2026 USA women's fashion
SEASONAL_KEYWORDS: Dict[int, Dict[str, Any]] = {
    1: {  # January
        "event": "New Year & Winter Style",
        "keywords": ["winter outfit ideas", "cozy knitwear women", "cold weather fashion", "winter layer style", "new year wardrobe"],
        "hashtags": ["#WinterFashion2026", "#CozyOutfit", "#ColdWeatherStyle", "#WinterWomensWear"]
    },
    2: {  # February
        "event": "Valentine's Day & Early Spring",
        "keywords": ["valentine's day outfit", "date night look", "romantic dresses women", "spring transition fashion"],
        "hashtags": ["#ValentinesDayOutfit", "#DateNightStyle", "#RomanticFashion", "#SpringTransition"]
    },
    3: {  # March
        "event": "Spring Break & Resort Wear",
        "keywords": ["spring break outfit ideas", "resort wear fashion", "vacation style women", "spring midi dresses", "lightweight tops"],
        "hashtags": ["#SpringBreakStyle", "#ResortWear2026", "#SpringFashionUSA", "#VacationOutfit"]
    },
    4: {  # April
        "event": "Easter & Spring Outfits",
        "keywords": ["easter dress ideas", "spring Sunday outfits", "pastel fashion women", "floral midi dress", "spring boutique looks"],
        "hashtags": ["#EasterOutfit", "#SpringDresses", "#PastelFashion", "#SpringStyleInspo"]
    },
    5: {  # May
        "event": "Mother's Day & Graduation",
        "keywords": ["mother's day gift style", "graduation guest dress", "spring event outfit", "outdoor brunch style"],
        "hashtags": ["#MothersDayOutfit", "#GraduationGuest", "#BrunchOutfit", "#MayFashion"]
    },
    6: {  # June
        "event": "Summer Kickoff & Wedding Guest",
        "keywords": ["summer wedding guest dress", "summer fashion 2026", "sun dress style", "coastal chic outfits"],
        "hashtags": ["#SummerWeddingGuest", "#SummerOutfits2026", "#CoastalChic", "#SunDressStyle"]
    },
    7: {  # July
        "event": "4th of July & Summer Vacation",
        "keywords": ["4th of july outfit ideas", "summer vacation style", "patriotic fashion women", "beach to dinner outfit", "hot summer style"],
        "hashtags": ["#4thOfJulyOutfit", "#SummerVacationStyle", "#PatrioticFashion", "#BeachToDinner"]
    },
    8: {  # August
        "event": "Back to School & Late Summer",
        "keywords": ["back to school outfits women", "teacher outfit ideas", "late summer style", "transition into fall fashion", "everyday casual style"],
        "hashtags": ["#BackToSchoolStyle", "#TeacherOutfit", "#LateSummerFashion", "#FallTransition"]
    },
    9: {  # September
        "event": "Labor Day & Fall Fashion",
        "keywords": ["labor day weekend outfit", "fall 2026 fashion trends", "fall layer style", "shackets and sweaters", "autumn boutique clothing"],
        "hashtags": ["#FallFashion2026", "#AutumnOutfits", "#ShacketStyle", "#LaborDayLook"]
    },
    10: { # October
        "event": "Halloween & Cozy Fall",
        "keywords": ["cozy fall outfits", "pumpkin patch outfit ideas", "fall booties and denim", "spooky season cozy looks"],
        "hashtags": ["#FallOutfitIdeas", "#CozyFallStyle", "#PumpkinPatchOutfit", "#FallLayering"]
    },
    11: { # November
        "event": "Thanksgiving & Early Holiday",
        "keywords": ["thanksgiving outfit ideas", "friendsgiving look", "cozy holiday style", "black friday fashion deals", "fall dinner outfit"],
        "hashtags": ["#ThanksgivingOutfit", "#FriendsgivingStyle", "#HolidayFashion", "#BlackFridayFinds"]
    },
    12: { # December
        "event": "Holiday Parties & Christmas",
        "keywords": ["holiday party dress", "christmas outfit women", "new year's eve outfit", "festive style ideas", "winter glam outfits"],
        "hashtags": ["#HolidayPartyOutfit", "#ChristmasStyle", "#NYEOutfit", "#FestiveFashion"]
    }
}

OCCASION_KEYWORDS = {
    "dress": ["date night dress", "wedding guest outfit", "brunch dress", "vacation midi dress", "office to dinner dress"],
    "top": ["casual work top", "weekend blouse", "everyday chic top", "layered outfit top", "going out top"],
    "jeans": ["high waisted denim", "flattering jeans women", "everyday casual jeans", "chic mom jeans", "trendy straight leg jeans"],
    "jacket": ["fall layering jacket", "stylish outerwear women", "chic shacket outfit", "casual blazer look"],
    "pants": ["comfy casual pants", "tailored work pants", "stylish leggings outfit", "lounge to errand look"],
    "sweater": ["cozy knit sweater", "fall sweater outfit", "soft oversized knit", "chic cardigan style"],
    "bag": ["everyday tote bag", "trendy crossbody purse", "travel backpack women", "chic handbag style"],
    "shoe": ["comfy stylish flats", "versatile boots women", "casual walking shoes", "chic everyday footwear"],
    "default": ["everyday boutique fashion", "trending US womens style", "chic versatile outfit", "affordable luxury style"]
}

DEMOGRAPHIC_TAGS = [
    "#WomensFashionUSA", "#USABoutique", "#ShopSmallUSA", "#AmericanWomensStyle",
    "#ChicStyleUSA", "#EverydayWomensStyle", "#TrendyBoutiqueFinds", "#AffordableFashionUSA"
]

PRICE_ANCHORS = ["Affordable US Boutique", "Free US Shipping", "Trendy Style Under $50", "Chic Fashion USA"]


def get_seo_content(product_type: str = "", tags: List[str] = None) -> Dict[str, Any]:
    """
    Get comprehensive Pinterest SEO term package based on current month, product category, and tags.
    """
    month = datetime.now().month
    seasonal = SEASONAL_KEYWORDS.get(month, SEASONAL_KEYWORDS[7])
    
    # Determine category occasion terms
    cat = "default"
    if product_type:
        p_lower = product_type.lower()
        for k in OCCASION_KEYWORDS:
            if k in p_lower:
                cat = k
                break
                
    occasions = OCCASION_KEYWORDS.get(cat, OCCASION_KEYWORDS["default"])
    
    return {
        "event_name": seasonal["event"],
        "seasonal_keywords": seasonal["keywords"],
        "seasonal_hashtags": seasonal["hashtags"],
        "occasion_keywords": occasions,
        "demographic_tags": DEMOGRAPHIC_TAGS,
        "price_anchors": PRICE_ANCHORS
    }
