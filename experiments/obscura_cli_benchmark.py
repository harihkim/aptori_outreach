"""
Obscura Multi-Endpoint CLI Benchmark Script (Conforming)

Tests Obscura Standard vs Stealth builds across 6 Reddit targets:
- Modern Thread
- Old Reddit Thread
- JSON stream
- Subreddit Listing (Modern)
- Subreddit Listing (Old)
- Search Query

Emits clean JSON metrics strictly adhering to the recorded evaluation schema.
"""

import subprocess
import json
import time
import os
import re
import hashlib

OBSCURA_BIN = os.getenv("OBSCURA_BIN", "/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/obscura")
OBSCURA_STEALTH_BIN = os.getenv("OBSCURA_STEALTH_BIN", "/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/stealth/obscura")

TEST_URLS = [
    {
        "name": "known_thread_modern_reddit",
        "url": "https://www.reddit.com/r/AskRobotics/comments/1uxx2bs/is_robotics_industry_broken/",
        "type": "thread"
    },
    {
        "name": "known_thread_old_reddit",
        "url": "https://old.reddit.com/r/AskRobotics/comments/1uxx2bs/is_robotics_industry_broken/",
        "type": "thread"
    },
    {
        "name": "known_thread_json",
        "url": "https://www.reddit.com/r/AskRobotics/comments/1uxx2bs/is_robotics_industry_broken.json",
        "type": "json"
    },
    {
        "name": "subreddit_listing_modern",
        "url": "https://www.reddit.com/r/cybersecurity/",
        "type": "listing"
    },
    {
        "name": "subreddit_listing_old",
        "url": "https://old.reddit.com/r/cybersecurity/",
        "type": "listing"
    },
    {
        "name": "reddit_search_query",
        "url": "https://www.reddit.com/r/cybersecurity/search/?q=API+security&restrict_sr=1",
        "type": "search"
    }
]

def get_file_sha256(filepath):
    try:
        with open(filepath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None

def run_obscura_test(bin_path, args, timeout=45):
    cmd = [bin_path] + args
    start_time = time.time()
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            text=True
        )
        elapsed = time.time() - start_time
        return {
            "returncode": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "latency_seconds": round(elapsed, 3),
            "timed_out": False
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": -1,
            "stdout": e.stdout if e.stdout else "",
            "stderr": e.stderr if e.stderr else "",
            "latency_seconds": round(time.time() - start_time, 3),
            "timed_out": True
        }

def analyze_content(stdout_text, stderr_text, test_type):
    combined = (stdout_text or "") + " " + (stderr_text or "")
    
    bot_block = False
    block_reason = None
    if "Blocked" in combined or "captcha" in combined.lower() or "bot challenge" in combined.lower():
        bot_block = True
        block_reason = "Bot/Captcha text detected"
    elif "403 Forbidden" in combined or "HTTP 403" in combined or "429 Too Many" in combined:
        bot_block = True
        block_reason = "HTTP 403/429 status"
    elif "Whoa there, pardner!" in combined:
        bot_block = True
        block_reason = "Reddit rate limit splash page"
        
    has_title = False
    has_body = False
    has_comments = False
    extracted_links_count = 0
    completeness_level = 0
    
    if test_type == "json":
        # Check if valid JSON was returned
        try:
            parsed = json.loads(stdout_text)
            if isinstance(parsed, list) and len(parsed) > 0:
                has_title = True
                has_body = True
                has_comments = True
                completeness_level = 4
            else:
                completeness_level = 1
        except Exception:
            # Fallback if raw text stream
            if len(stdout_text) > 1000:
                completeness_level = 2
            else:
                completeness_level = 0
    elif test_type == "thread":
        if "Is robotics industry broken" in combined or "robotics industry" in combined.lower():
            has_title = True
        if "jacobian" in combined.lower() or "freelancer" in combined.lower() or "academia" in combined.lower():
            has_body = True
        if "shreddit-comment" in combined.lower() or "qthqq" in combined.lower():
            has_comments = True
            
        if has_title and has_body and has_comments:
            completeness_level = 4
        elif has_title and has_body:
            completeness_level = 3
        elif has_title:
            completeness_level = 1
        else:
            completeness_level = 0
    elif test_type in ["listing", "search"]:
        reddit_links = re.findall(r'https?://[^\s]+/r/[A-Za-z0-9_]+/comments/[^\s\)]+', combined)
        extracted_links_count = len(set(reddit_links))
        if extracted_links_count > 1:
            has_title = True
            has_body = True
            completeness_level = 3
        elif len(combined) > 2000:
            completeness_level = 1
        else:
            completeness_level = 0
            
    return {
        "bot_block": bot_block,
        "block_reason": block_reason,
        "content_length_chars": len(stdout_text) if stdout_text else 0,
        "has_title": has_title,
        "has_body": has_body,
        "has_comments": has_comments,
        "extracted_links_count": extracted_links_count,
        "completeness_level": completeness_level
    }

def main():
    run_id = f"cli_bench_{int(time.time())}"
    results = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "binaries": {
            "standard_path": OBSCURA_BIN,
            "standard_sha256": get_file_sha256(OBSCURA_BIN),
            "stealth_path": OBSCURA_STEALTH_BIN,
            "stealth_sha256": get_file_sha256(OBSCURA_STEALTH_BIN)
        },
        "tests": []
    }
    
    for item in TEST_URLS:
        url = item["url"]
        name = item["name"]
        t_type = item["type"]
        
        # Test Standard
        res_std = run_obscura_test(OBSCURA_BIN, ["fetch", "--dump", "markdown", url])
        analysis_std = analyze_content(res_std["stdout"], res_std["stderr"], t_type)
        
        # Test Stealth
        res_stl = run_obscura_test(OBSCURA_STEALTH_BIN, ["fetch", "--stealth", "--dump", "markdown", url])
        analysis_stl = analyze_content(res_stl["stdout"], res_stl["stderr"], t_type)
        
        results["tests"].append({
            "test_name": name,
            "url": url,
            "type": t_type,
            "standard": {
                "latency_seconds": res_std["latency_seconds"],
                "returncode": res_std["returncode"],
                "analysis": analysis_std
            },
            "stealth": {
                "latency_seconds": res_stl["latency_seconds"],
                "returncode": res_stl["returncode"],
                "analysis": analysis_stl
            }
        })
        time.sleep(1)
        
    out_file = os.path.join(os.path.dirname(__file__), "2026-08-20-obscura-test-result.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[+] Saved conforming CLI benchmark results to {out_file}")

if __name__ == "__main__":
    main()
