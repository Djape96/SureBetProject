# 🎯 SureBet Koyeb Deployment - Quick Start

## ✅ Changes Pushed to GitHub

All fixes have been committed and pushed to your repository.

## 🔧 What Was Fixed

### The Problem
- Scripts were **timing out after 2 minutes** on Koyeb
- **Infinite scroll loop** was running indefinitely
- Too many **retry attempts** slowed down execution

### The Solution
1. ✅ **Timeout increased**: 120s → 180s in main_runner
2. ✅ **Retries reduced**: 2 → 1 for faster execution  
3. ✅ **Infinite scroll limited**: Max 15 iterations
4. ✅ **Runtime optimized**: 90s max per script

**Result:** Each cycle now completes in ~60-90 seconds instead of timing out!

## 🚀 Deploy to Koyeb NOW

### Step 1: Go to Koyeb
👉 https://app.koyeb.com/

### Step 2: Create New Service
1. Click **"Create Web Service"**
2. Choose **GitHub** 
3. Select repository: **Djape96/SureBetProject**
4. Branch: **main**

### Step 3: Configure Build
- **Builder**: Dockerfile (auto-detected)
- **Dockerfile path**: `Dockerfile`
- Keep default settings

### Step 4: Configure Environment Variables

Click **"Environment Variables"** and add these **REQUIRED** variables:

```
TELEGRAM_BOT_TOKEN = your_bot_token_here
TELEGRAM_CHAT_ID = your_chat_id_here
```

**IMPORTANT:** Remove or set these to `0` if they exist from previous deployments:
```
BASKETBALL_FORCE_REQUESTS = 0
BASKETBALL_DISABLE_SELENIUM = 0
PLAYER_SPECIALS_FORCE_REQUESTS = 0
```

**Don't have Telegram credentials?** Run locally:
```bash
python get_chat_id.py YOUR_BOT_TOKEN
```

### Step 5: Choose Instance
- **Type**: **Nano** (Free tier - sufficient for this project)
- **Region**: Frankfurt or closest to you
- **Scaling**: 1 instance

### Step 6: Deploy!
Click **"Deploy"** button

## 📊 What to Expect

### Build Time
⏱️ **3-5 minutes** - Installing Chrome, dependencies, etc.

### After Deployment
```
[08:52:00] 🚀 SureBet Arbitrage Runner Started
[08:52:00] 🔁 Starting cycle #1
[08:52:00] ============================================================
[08:52:05] ✅ arbitrage_tennis.py completed successfully  
[08:52:25] ✅ enhanced_basketball_analyzer.py completed successfully
[08:52:55] ✅ enhanced_player_specials_analyzer.py completed successfully
[08:53:00] 📊 Cycle #1 complete - ✅ 3 succeeded, ❌ 0 failed
[08:53:00] 📱 Telegram notification sent
[08:53:00] ⏳ Waiting 300 seconds until next cycle...
```

### Running Schedule
- ✅ Runs **every 5 minutes** (300 seconds)
- ✅ Scans: Tennis → Basketball → Player Specials
- ✅ Sends Telegram notification after each cycle
- ✅ Runs 24/7 automatically

## 🔍 Monitoring

### View Logs in Koyeb
1. Go to your service
2. Click **"Logs"** tab
3. Watch real-time execution

### Telegram Notifications
You'll receive messages like:
```
🔄 Cycle #1 Complete
✅ 3 scripts succeeded
❌ 0 scripts failed

Check surebet files for opportunities!
```

## ⚠️ Troubleshooting

### If scripts still timeout:
Add these environment variables in Koyeb:
```
BASKETBALL_MAX_RUNTIME = 60
PLAYER_SPECIALS_MAX_RUNTIME = 60
```

### If no Telegram messages:
1. Check environment variables are set correctly
2. Test locally: `python env_check.py`

### If Chrome/Selenium errors:
Check logs for specific errors - the Dockerfile includes all Chrome dependencies

## 💰 Cost

**FREE** on Koyeb nano instance (512MB RAM)

Enough for this project! Only upgrade if you need faster execution.

## 📝 Next Steps

1. ✅ Deploy to Koyeb (follow steps above)
2. ✅ Watch first cycle complete successfully
3. ✅ Verify Telegram notifications arrive
4. ✅ Monitor for surebets!

## 🆘 Need Help?

Check the detailed guide: **KOYEB_DEPLOYMENT.md**

Or test locally first:
```bash
python main_runner.py
```

---

**Ready? Go deploy! 🚀**
