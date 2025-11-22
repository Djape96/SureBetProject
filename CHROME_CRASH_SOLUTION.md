# 🚨 Chrome Crashing on Koyeb - Solution Guide

## The Problem

Chrome is starting but immediately crashing when trying to navigate:
```
InvalidSessionIdException: session deleted as the browser has closed the connection
from disconnected: not connected to DevTools
```

This is happening because **Koyeb's nano instance doesn't have enough resources** for Chrome.

## Solution Options (Pick One)

### ⭐ Option 1: Upgrade to Small Instance (RECOMMENDED)

**Cost:** $5.40/month (vs Free nano)

**Steps:**
1. Go to Koyeb → Your Service → Settings → Instance
2. Change from **"nano"** to **"small"**  
3. Click **"Save"** and wait for redeploy

**Why this works:**
- Small instance has **2GB RAM** vs 512MB on nano
- Chrome needs ~500-800MB to run headless
- Nano is too small for Selenium/Chrome

### Option 2: Use Render.com Instead (Free Tier Available)

Render has better free tier specs:
- **512MB RAM** (same as Koyeb nano)
- But **better /dev/shm** (shared memory) configuration
- Chrome works better on Render's free tier

**Steps:**
1. Go to [render.com](https://render.com)
2. Create new **Web Service**
3. Connect GitHub repo
4. Use same Dockerfile
5. Add environment variables
6. Deploy

### Option 3: Deploy to Railway.app (Free $5 credit/month)

Railway gives $5/month free credit:
- Usually enough for this project
- Better container resources than Koyeb nano
- Easy deployment

### Option 4: Disable Selenium (Fast/Limited Mode)

Run without Selenium (requests-only mode):

**Add to Koyeb environment variables:**
```
BASKETBALL_FORCE_REQUESTS=1
PLAYER_SPECIALS_FORCE_REQUESTS=1
```

**Pros:**
- Works on nano instance
- Very fast execution
- No Chrome crashes

**Cons:**
- May get less data (if site requires JavaScript)
- Might miss some matches

## Recommendation

**For production use:** Upgrade to **Small instance** on Koyeb ($5.40/month)

**For testing:** Try **Render.com free tier** or **Railway** first

**For minimal cost:** Use **requests-only mode** but accept limited data

## Current Status

Your deployment is working except Chrome crashes. All other parts work:
- ✅ Tennis analyzer works (no Selenium needed)
- ✅ Main runner works
- ✅ Telegram notifications work  
- ❌ Basketball analyzer fails (needs Selenium)
- ❌ Player specials fails (needs Selenium)

## Quick Fix Right Now

**Temporary solution while you decide:**

1. Go to Koyeb → Environment Variables
2. Add:
   ```
   BASKETBALL_FORCE_REQUESTS=1
   ```
3. This will make basketball skip Selenium
4. At least tennis will work and notify you

**Then decide** if you want to upgrade instance or try different platform.

## Why This Happened

Chrome + Selenium in headless mode needs:
- Minimum ~500MB RAM
- Proper /dev/shm (shared memory)
- Process isolation support

Koyeb nano (512MB) shares that RAM with:
- Python runtime (~100MB)
- Your app code (~50MB)
- System overhead (~100MB)
- **Only ~262MB left** for Chrome → **Not enough!**

---

**Bottom line: You need a bigger instance or different platform for Selenium to work. 🎯**
