import json
import requests
import os
from datetime import datetime, timedelta, timezone

LEETCODE_COM_URL = "https://leetcode.com/graphql"
LEETCODE_CN_URL = "https://leetcode.cn/graphql"

def get_leetcode_stats(username):
    # Query for LeetCode.com (Stats Only)
    query_com = """
    query userSessionProgress($username: String!) {
      matchedUser(username: $username) {
        submitStats {
          acSubmissionNum {
            difficulty
            count
          }
        }
      }
    }
    """

    # Query for LeetCode.cn (Recent Submissions)
    query_cn_recent = """
    query recentSubmissions($userSlug: String!) {
      recentSubmissions(userSlug: $userSlug) {
        status
        submitTime
        question {
          questionFrontendId
        }
      }
    }
    """

    # Query for LeetCode.cn (Stats Only)
    query_cn_stats = """
    query userProfileUserQuestionProgress($userSlug: String!) {
      userProfileUserQuestionProgress(userSlug: $userSlug) {
        numAcceptedQuestions {
          difficulty
          count
        }
      }
    }
    """

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://leetcode.com',
        'Content-Type': 'application/json'
    }
    
    # --- Try LeetCode.com ---
    # (Keeping existing logic for .com as fallback or for mixed usage, 
    #  but prioritizing CN specific logic for recent submissions if possible. 
    #  For now, we'll return a dict with extra info)
    
    try:
        response = requests.post(LEETCODE_COM_URL, json={'query': query_com, 'variables': {"username": username}}, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data') and data['data'].get('matchedUser'):
                matched = data['data']['matchedUser']
                stats = matched['submitStats']['acSubmissionNum']
                total_ac = next(item['count'] for item in stats if item['difficulty'] == 'All')
                print(f"Successfully fetched {username} from {LEETCODE_COM_URL}")
                # For .com, we lack the handy recentSubmissions query in this context, 
                # so we might stick to baseline logic or try to add it later.
                return {"total_ac": total_ac, "week_solved": None} 
    except Exception as e:
        print(f"Error fetching {username} from {LEETCODE_COM_URL}: {e}")

    # --- Try LeetCode.cn ---
    try:
        # 1. Fetch Total Stats
        total_ac = 0
        response_stats = requests.post(LEETCODE_CN_URL, json={'query': query_cn_stats, 'variables': {"userSlug": username}}, headers=headers, timeout=10)
        if response_stats.status_code == 200:
            data = response_stats.json()
            if data.get('data') and data['data'].get('userProfileUserQuestionProgress'):
                stats = data['data']['userProfileUserQuestionProgress']['numAcceptedQuestions']
                total_ac = sum(item['count'] for item in stats)
            else:
                return None
        
        # 2. Fetch Recent Submissions for Weekly Count
        week_solved_count = 0
        response_recent = requests.post(LEETCODE_CN_URL, json={'query': query_cn_recent, 'variables': {"userSlug": username}}, headers=headers, timeout=10)
        if response_recent.status_code == 200:
            data_recent = response_recent.json()
            if data_recent.get('data') and data_recent['data'].get('recentSubmissions'):
                submissions = data_recent['data']['recentSubmissions']
                
                # Calculate start of week (Monday 00:00 UTC)
                now = datetime.now(timezone.utc)
                days_since_monday = now.weekday()
                start_of_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
                start_ts = start_of_week.timestamp()
                
                # Filter submissions: 
                # 1. After start of week
                # 2. Status is 'A_10' (Accepted)
                # 3. Unique questions
                solved_questions = set()
                for sub in submissions:
                    if sub['submitTime'] >= start_ts and sub['status'] == 'A_10':
                        solved_questions.add(sub['question']['questionFrontendId'])
                
                week_solved_count = len(solved_questions)
                print(f"Calculated {week_solved_count} unique problems solved since {start_of_week}")

        print(f"Successfully fetched {username} from {LEETCODE_CN_URL}")
        return {"total_ac": total_ac, "week_solved": week_solved_count}

    except Exception as e:
        print(f"Error fetching {username} from {LEETCODE_CN_URL}: {e}")
    
    print(f"User {username} not found on .com or .cn")
    return None

def main():
    with open('data/users.json', 'r') as f:
        usernames = json.load(f)

    stats_file = 'data/stats.json'
    if os.path.exists(stats_file):
        with open(stats_file, 'r') as f:
            all_stats = json.load(f)
    else:
        all_stats = {}

    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    current_iso_week = datetime.now(timezone.utc).isocalendar()[1]

    for username in usernames:
        result = get_leetcode_stats(username)
        if result is None:
            continue
            
        current_total = result["total_ac"]
        week_solved = result["week_solved"] # Precise count from recent submissions

        if username not in all_stats:
            all_stats[username] = {
                "baseline": current_total,
                "current": current_total,
                "week": current_iso_week,
                "history": []
            }
        
        # Reset baseline if it's a new week
        if all_stats[username].get("week") != current_iso_week:
            # Archive previous week logic...
            previous_week = all_stats[username].get("week")
            # If we had a precise count last week, we could use that, but 'baseline' diff is safer for archiving
            # unless we stored 'week_solved' in the state. 
            # For simplicity, we stick to baseline diff for archiving, but use week_solved for display.
            previous_baseline = all_stats[username].get("baseline", 0)
            previous_current = all_stats[username].get("current", 0)
            solved_count = previous_current - previous_baseline
            
            if previous_week:
                all_stats[username]["history"].append({
                    "week": previous_week,
                    "year": datetime.now().year,
                    "solved": solved_count
                })
            
            all_stats[username]["baseline"] = current_total
            all_stats[username]["week"] = current_iso_week
        
        all_stats[username]["current"] = current_total
        all_stats[username]["last_updated"] = today_str
        
        # Store the precise count for display
        if week_solved is not None:
             all_stats[username]["week_solved"] = week_solved
        else:
             # Fallback for .com or errors
             all_stats[username]["week_solved"] = current_total - all_stats[username]["baseline"]

    with open(stats_file, 'w') as f:
        json.dump(all_stats, f, indent=2)

if __name__ == "__main__":
    main()
