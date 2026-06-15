"""Try EM F10 page for industry data"""
import httpx, json, re

headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://f10.eastmoney.com/"}

with httpx.Client(headers=headers, timeout=15, verify=False) as client:
    # EM F10 Company Survey page - contains industry info
    url = "http://f10.eastmoney.com/f10_v2/CompanySurvey.aspx?code=sz000001"
    try:
        resp = client.get(url)
        print(f"F10 page: {resp.status_code}, len={len(resp.text)}")
        if resp.status_code == 200:
            # Look for industry in the HTML
            text = resp.text
            # Search for industry-related patterns
            match = re.search(r'所属行业[：:]\s*([^<]+)', text)
            if match:
                print(f"Industry found: {match.group(1)}")
            else:
                # Print context around "行业"
                for m in re.finditer(r'[^。]*?行业[^。]*?。', text):
                    print(f"  Context: {m.group()}")
                # Print first 1000 chars
                print(text[:1000])
    except Exception as e:
        print(f"F10 page failed: {e}")

    # Try an alternative EM F10 URL
    url2 = "http://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax?code=000001"
    try:
        resp = client.get(url2)
        print(f"\nF10 ajax: {resp.status_code}, len={len(resp.text)}")
        if resp.status_code == 200:
            print(resp.text[:500])
    except Exception as e:
        print(f"F10 ajax failed: {e}")
