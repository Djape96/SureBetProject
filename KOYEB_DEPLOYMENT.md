# Koyeb Deployment Guide for SureBet Project

## Quick Summary

The timeout issues were caused by:
1. Scripts taking longer than the 120s timeout in `main_runner.py`
2. Infinite scroll loops in `enhanced_player_specials_analyzer.py` running indefinitely
3. Too many retry attempts in Selenium scraping

## Fixes Applied

1. **Increased timeout** in `main_runner.py` from 120s → 180s (3 minutes)
2. **Reduced retries** from 2 → 1 for both basketball and player_specials
3. **Added max iteration limit** (15) to infinite scroll loop in player_specials
4. **Reduced max_runtime** for player_specials from 120s → 90s
5. **Basketball uses 90s max_runtime** with 1 retry

Expected execution times now:
- Tennis: ~5-10 seconds
- Basketball: ~10-20 seconds  
- Player Specials: ~30-60 seconds
- **Total per cycle: ~1-2 minutes** (well under 180s timeout)

## Deployment Steps

### 1. Push Your Code to GitHub

```bash
cd C:\Users\Jelena\Downloads\SureBet_Project_update\SureBet_Project\SureBet_Project
git add .
git commit -m "Fix timeout issues for Koyeb deployment"
git push origin main
```

### 2. Set Up Koyeb

1. Go to [koyeb.com](https://www.koyeb.com) and log in
2. Click **Create Web Service**
3. Choose **GitHub** as the deployment method
4. Select your repository: `Djape96/SureBetProject`
5. Choose branch: `main`

### 3. Configure Build Settings

**Build Configuration:**
- **Builder**: Dockerfile
- **Dockerfile**: `Dockerfile` (auto-detected)
- **Context**: `/` (root of repo)

### 4. Configure Environment Variables

Add these environment variables in Koyeb dashboard:

**Required:**

| Variable | Value | Description |
|----------|-------|-------------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | `987654321` | Your Telegram chat ID |

**IMPORTANT - Remove or set to 0 if present from old deployments:**

| Variable | Value | Description |
|----------|-------|-------------|
| `BASKETBALL_FORCE_REQUESTS` | `0` | Do NOT force requests-only mode |
| `BASKETBALL_DISABLE_SELENIUM` | `0` | Do NOT disable Selenium |
| `PLAYER_SPECIALS_FORCE_REQUESTS` | `0` | Do NOT force requests-only mode |
| `BASKETBALL_REQUEST_MIN_LEN` | DELETE | Remove if exists |

**Optional (only if you need to tune performance):**

| Variable | Value | Description |
|----------|-------|-------------|
| `BASKETBALL_MAX_RUNTIME` | `90` | Basketball scraper timeout |
| `PLAYER_SPECIALS_MAX_RUNTIME` | `90` | Player specials timeout |

**Get your Telegram credentials:**
```bash
# If you don't have them yet, run locally:
python get_chat_id.py YOUR_BOT_TOKEN
```

### 5. Configure Instance Settings

**Instance Type:**
- **Region**: Choose closest to you (e.g., `fra` for Frankfurt)
- **Instance**: `nano` or `small` (nano should be enough)
- **Scaling**: 1 instance (no auto-scaling needed)

**Health Checks:**
- **Port**: `8000` (optional, for health check endpoint)
- **Path**: `/` (optional)
- **Grace Period**: `30s`

### 6. Deploy

Click **Deploy** and wait for the build to complete (~3-5 minutes).

## Monitoring

### Check Logs

In Koyeb dashboard:
1. Go to your service
2. Click **Logs** tab
3. You should see output like:

```
[2025-11-22 08:52:00] 🚀 SureBet Arbitrage Runner Started
[2025-11-22 08:52:00] ============================================================
[2025-11-22 08:52:00] 🔁 Starting cycle #1
[2025-11-22 08:52:05] ✅ arbitrage_tennis.py completed successfully
[2025-11-22 08:52:25] ✅ enhanced_basketball_analyzer.py completed successfully
[2025-11-22 08:52:55] ✅ enhanced_player_specials_analyzer.py completed successfully
[2025-11-22 08:53:00] 📊 Cycle #1 complete - ✅ 3 succeeded, ❌ 0 failed
[2025-11-22 08:53:00] 📱 Telegram notification sent
[2025-11-22 08:53:00] ⏳ Waiting 300 seconds until next cycle...
```

### Expected Behavior

- **Cycle interval**: Every 5 minutes (300 seconds)
- **Scripts run**: tennis → basketball → player_specials
- **Telegram notifications**: After each cycle
- **No timeouts**: All scripts complete within 180s limit

## Troubleshooting

### If scripts still timeout:

1. **Reduce max_runtime further**:
   - Set `BASKETBALL_MAX_RUNTIME=60`
   - Set `PLAYER_SPECIALS_MAX_RUNTIME=60`

2. **Enable fast mode for basketball**:
   Edit `main_runner.py` line 21:
   ```python
   ('enhanced_basketball_analyzer.py', ['--fast', '--max-runtime', '60', '--retries', '1']),
   ```

3. **Check Chrome/Selenium issues**:
   - Ensure Dockerfile has all Chrome dependencies
   - Check if headless mode is working
   - Look for Chrome crash messages in logs

### If Telegram notifications don't work:

```bash
# Test locally first:
python env_check.py

# Get your chat ID:
python get_chat_id.py YOUR_BOT_TOKEN
```

### If health checks fail:

The main_runner.py doesn't expose a health endpoint. Either:
- **Disable health checks** in Koyeb
- Or create a simple health check file (optional)

## Files Modified

- `main_runner.py` - Increased timeout, added script arguments
- `enhanced_player_specials_analyzer.py` - Added iteration limit to infinite scroll
- `Dockerfile` - Already configured for Koyeb

## Cost Estimate

Koyeb Free Tier:
- **Free**: 1 nano instance (512MB RAM, 0.1 vCPU)
- **Enough for**: This project runs fine on nano

If you need more:
- **Small**: $5.40/month (2GB RAM, 1 vCPU)

## Next Steps

After deployment:
1. Watch logs for first few cycles
2. Verify Telegram notifications arrive
3. Check surebet detection is working
4. Adjust `CHECK_INTERVAL` in `main_runner.py` if needed (currently 5 minutes)

## Support

If you still have issues:
1. Check Koyeb logs for specific error messages
2. Test scripts locally with same arguments: `python enhanced_basketball_analyzer.py --max-runtime 90 --retries 1`
3. Verify Chrome/Selenium works in Dockerfile environment
