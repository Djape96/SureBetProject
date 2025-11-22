"""
Main runner script for continuous arbitrage detection.
Runs all arbitrage analyzers in a loop with configurable intervals.
"""

import time
import subprocess
import sys
from datetime import datetime
import os

# Start health check server for Koyeb
try:
    from health_server import start_health_server, update_health
    start_health_server(port=8000)
    HEALTH_ENABLED = True
except Exception as e:
    print(f"⚠️ Health server not started: {e}")
    HEALTH_ENABLED = False

# Try to import telegram notifier
try:
    from telegram_notifier import send_raw_message
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ Telegram notifier not available")

# Configuration
CHECK_INTERVAL = 300  # 5 minutes between checks (adjust as needed)
SCRIPTS_TO_RUN = [
    ('arbitrage_tennis.py', []),
    ('enhanced_basketball_analyzer.py', ['--max-runtime', '90', '--retries', '1']),
    ('arbitrage_football.py', []),  # Using simpler working version
    ('enhanced_player_specials_analyzer.py', ['--max-runtime', '90', '--retries', '1']),
]

def log(message):
    """Print timestamped log message"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    sys.stdout.flush()  # Ensure logs appear immediately

def run_script(script_config):
    """Run a single arbitrage script"""
    # Handle both old string format and new tuple format
    if isinstance(script_config, str):
        script_name = script_config
        script_args = []
    else:
        script_name, script_args = script_config
    
    if not os.path.exists(script_name):
        log(f"⚠️  Script not found: {script_name}")
        return False
    
    try:
        cmd = [sys.executable, script_name] + script_args
        log(f"🔄 Running {script_name} {' '.join(script_args)}...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout per script
        )
        
        if result.returncode == 0:
            log(f"✅ {script_name} completed successfully")
            if result.stdout:
                print(result.stdout)
            return True
        else:
            log(f"❌ {script_name} failed with code {result.returncode}")
            if result.stdout:
                print("STDOUT:", result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        log(f"⏱️  {script_name} timed out after 180 seconds")
        return False
    except KeyboardInterrupt:
        raise  # Re-raise to allow clean shutdown
    except Exception as e:
        log(f"❌ Error running {script_name}: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main loop - runs arbitrage scripts continuously"""
    log("=" * 60)
    log("🚀 SureBet Arbitrage Runner Started")
    log("=" * 60)
    log(f"Check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL//60} minutes)")
    log(f"Scripts to run: {len(SCRIPTS_TO_RUN)}")
    log("")
    
    # Update health status
    if HEALTH_ENABLED:
        update_health(status="running")
    
    # Send startup notification
    if TELEGRAM_AVAILABLE:
        try:
            startup_msg = "🚀 SureBet Runner Started!\n\nMonitoring:\n• Tennis\n• Basketball\n• Football\n• Player Specials\n\nChecking every 5 minutes..."
            send_raw_message(startup_msg)
            log("📱 Startup notification sent to Telegram")
        except Exception as e:
            log(f"⚠️ Telegram startup notification failed: {e}")
    
    cycle_count = 0
    
    while True:
        cycle_count += 1
        log("=" * 60)
        log(f"🔁 Starting cycle #{cycle_count}")
        log("=" * 60)
        
        successful = 0
        failed = 0
        
        for script in SCRIPTS_TO_RUN:
            if run_script(script):
                successful += 1
            else:
                failed += 1
            
            # Small delay between scripts
            time.sleep(5)
        
        log("")
        log(f"📊 Cycle #{cycle_count} complete - ✅ {successful} succeeded, ❌ {failed} failed")
        
        # Update health status
        if HEALTH_ENABLED:
            update_health(
                status="healthy" if failed == 0 else "degraded",
                last_cycle=datetime.now().isoformat()
            )
        
        # Send Telegram notification after each cycle
        if TELEGRAM_AVAILABLE:
            try:
                summary = f"🔄 Cycle #{cycle_count} Complete\n"
                summary += f"✅ {successful} scripts succeeded\n"
                summary += f"❌ {failed} scripts failed\n\n"
                summary += f"Check surebet files for opportunities!"
                send_raw_message(summary)
                log("📱 Telegram notification sent")
            except Exception as e:
                log(f"⚠️ Telegram notification failed: {e}")
        
        log(f"⏳ Waiting {CHECK_INTERVAL} seconds until next cycle...")
        log("")
        
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n⛔ Runner stopped by user")
        sys.exit(0)
    except Exception as e:
        log(f"\n💥 Fatal error: {str(e)}")
        sys.exit(1)
