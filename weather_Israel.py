from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright
import asyncio

mcp = FastMCP("weather-Israel")

FORECAST_URL = "https://www.weather2day.co.il/forecast"

# המשתנים ששומרים את מצב הדפדפן כדי שנוכל להמשיך מאותה נקודה
browser_instance = None
page_instance = None

@mcp.tool()
async def open_weather_forecast_israel() -> str:
    """
    פותח דפדפן ומנווט לדף של אתר מזג האוויר בישראל.
    """
    global browser_instance, page_instance
    
    try:
        if page_instance is None:
            pw = await async_playwright().start()
            browser_instance = await pw.chromium.launch(headless=False)
            context = await browser_instance.new_context(ignore_https_errors=True)
            page_instance = await context.new_page()
        
        # השינוי הקריטי: wait_until="domcontentloaded" מונע תקיעות על סקריפטים חסומים בנטפרי
        await page_instance.goto(FORECAST_URL, timeout=60000, wait_until="domcontentloaded")
        return "הדפדפן נפתח בהצלחה באתר weather2day."
        
    except Exception as e:
        # עכשיו הוא יהיה חייב להגיד לנו מה הבעיה בלי לסנן!
        return f"שגיאה קריטית, עליך לדווח למשתמש את השגיאה הזו בדיוק מילה במילה: {str(e)}"
    
@mcp.tool()
async def enter_weather_forecast_city_israel(city_name: str) -> str:
    """
    מזין את שם העיר בתיבת החיפוש באתר. 
    """
    global page_instance
    if page_instance is None:
        return "Error: הדפדפן לא פתוח. הפעל קודם את open_weather_forecast_israel."
    
    try:
        # פגענו בול: שימוש ב-ID הייחודי שמצאת בעצמך!
        search_box = page_instance.locator("#city_search_forecast")
        
        await search_box.wait_for(state="visible", timeout=15000)
        await search_box.click() # פוקוס על התיבה
        
        await search_box.fill(city_name)
        
        # נותנים לאתר חצי שנייה לעכל את ההקלדה
        await page_instance.wait_for_timeout(500)
        
        return f"הוקלד שם העיר {city_name} בתיבת החיפוש."
    except Exception as e:
        return f"שגיאה קריטית, עליך לדווח למשתמש את השגיאה הזו בדיוק מילה במילה: {str(e)}"
    
@mcp.tool()
async def select_weather_forecast_city_israel() -> str:
    """
    בוחר את התוצאה שקפצה ברשימה הנפתחת באמצעות מקשי המקלדת (חץ למטה ואז אנטר).
    """
    global page_instance
    if page_instance is None:
        return "Error: הדפדפן לא פתוח."
    
    try:
        # פשוט נשתמש במקלדת בדיוק כמו שעשית בבדיקה הידנית!
        await page_instance.keyboard.press("ArrowDown") # יורד לבחירה הראשונה
        await page_instance.wait_for_timeout(300)       # המתנה קטנטנה
        await page_instance.keyboard.press("Enter")     # לחיצה על אנטר לבחירה
        
        # מחכים שהדף ייטען עם הנתונים החדשים של העיר שנבחרה
        await page_instance.wait_for_timeout(2000)
        
        return "נבחרה העיר הראשונה מהרשימה באמצעות המקלדת. כעת הדף מציג את התחזית לעיר זו."
    except Exception as e:
        print(f"\n--- Playwright Error in select_city: {str(e)} ---\n")
        return f"שגיאה בבחירת העיר: {str(e)}"
    
@mcp.tool()
async def get_weather_data_from_page() -> str:
    """
    מחלץ את תוכן התחזית מהדף הנוכחי בדפדפן ומחזיר אותו כטקסט ל-LLM.
    יש לקרוא לכלי זה רק לאחר שהדף נטען עם העיר המבוקשת.
    """
    global page_instance
    if page_instance is None:
        return "Error: הדפדפן לא פתוח."
    
    try:
        # שליפת הטקסט מתוך הדף.
        # אנחנו מגבילים ל-2000 תווים כדי לא להעמיס יותר מדי טקסט לא רלוונטי על המודל
        text = await page_instance.inner_text("body")
        return f"להלן המידע שנמצא בדף (יש לקרוא ולסכם את התחזית מתוכו):\n\n{text[:2000]}"
    except Exception as e:
        return f"שגיאה בחילוץ נתונים: {str(e)}"    

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()