# 🔧 URGENT FIX: Basketball Analyzer Not Using Selenium

## The Problem

Your Koyeb logs show:
```
[07:54:47] 🏀 Params ... requests_only=True ...
❌ Requests response insufficient and Selenium disabled (requests-only/fast mode).
```

This means Selenium is disabled due to an **old environment variable** from a previous deployment.

## The Fix (Do This Now!)

### Go to Your Koyeb Service

1. Open your service in Koyeb dashboard
2. Click **"Settings"** tab
3. Scroll to **"Environment Variables"** section

### Remove/Fix These Variables

**DELETE or SET TO `0`:**

- `BASKETBALL_FORCE_REQUESTS` → DELETE or set to `0`
- `BASKETBALL_DISABLE_SELENIUM` → DELETE or set to `0`  
- `BASKETBALL_REQUEST_MIN_LEN` → DELETE
- `PLAYER_SPECIALS_FORCE_REQUESTS` → DELETE or set to `0`

### Keep These Variables

**KEEP (Required):**
- `TELEGRAM_BOT_TOKEN` = your actual token
- `TELEGRAM_CHAT_ID` = your actual chat ID

### After Fixing

1. Click **"Save"** 
2. Koyeb will automatically **redeploy**
3. Wait 2-3 minutes for rebuild
4. Check logs again

## What You Should See After Fix

```
[08:00:00] 🏀 Starting basketball live data acquisition
[08:00:00] 🏀 Params ... requests_only=False ... max_runtime=90
[08:00:00] 🏀 Attempting simple requests fetch...
[08:00:01] 🏀 Requests status=200 size=1016 took=0.8s
[08:00:01] 🏀 Requests response insufficient; will consider Selenium
[08:00:01] 🏀 Importing Selenium stack...
[08:00:02] 🏀 Selenium imports successful
[08:00:02] 🏀 Selenium attempt 1/2 (elapsed 1s)
[08:00:02] 🏀 Provisioning ChromeDriver...
[08:00:08] 🏀 WebDriver instance created
[08:00:08] 🏀 Navigating to basketball URL...
[08:00:12] 🏀 Page body detected (nav 3.8s)
[08:00:15] 🏀 Finished initial scrolling phase
[08:00:15] 🏀 Collected decimals count=117 page_source_len=771775
[08:00:15] 🏀 ✅ Basketball live data via Selenium (content threshold met)
[08:00:15] 🏀 Quitting WebDriver
📊 Parsed 20 basketball matches
```

Notice:
- ✅ `requests_only=False` (not True!)
- ✅ Selenium runs successfully
- ✅ Matches are parsed

## Why This Happened

You probably had these environment variables set from testing or a previous deployment attempt. The script reads them and disables Selenium when:

```python
env_force_requests = os.environ.get('BASKETBALL_FORCE_REQUESTS','0')=='1'
env_disable_selenium = os.environ.get('BASKETBALL_DISABLE_SELENIUM','0')=='1'
```

## Test Locally First (Optional)

If you want to verify before redeploying:

```bash
# Make sure these are NOT set locally
Remove-Item Env:BASKETBALL_FORCE_REQUESTS -ErrorAction SilentlyContinue
Remove-Item Env:BASKETBALL_DISABLE_SELENIUM -ErrorAction SilentlyContinue

# Run the script
python enhanced_basketball_analyzer.py --max-runtime 90 --retries 1 --verbose
```

You should see Selenium run and parse matches successfully.

## Summary

**DO THIS:**
1. Go to Koyeb → Your Service → Settings → Environment Variables
2. Delete: `BASKETBALL_FORCE_REQUESTS`, `BASKETBALL_DISABLE_SELENIUM`, `BASKETBALL_REQUEST_MIN_LEN`
3. Keep: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
4. Save and wait for redeploy
5. Check logs - should see Selenium running now!

---

**After fixing, your next cycle should complete successfully! 🎉**
