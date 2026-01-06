import json
import requests
import os
from datetime import datetime, timedelta, timezone

LEETCODE_COM_URL = "https://leetcode.com/graphql"
LEETCODE_CN_URL = "https://leetcode.cn/graphql"

def get_recent_submissions(username, region="CN"):
    """
    Returns a list of unique problems solved in the current week (Monday 00:00 UTC start).
    Format: [{"id": "1", "diff": "Easy"}, ...]
    """
    
    # Calculate start of week (Monday 00:00 UTC)
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    start_of_week = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_ts = start_of_week.timestamp()

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
    
    query_com_recent = """
    query recentAcSubmissions($username: String!) {
      recentAcSubmissionList(username: $username, limit: 50) {
        title
        timestamp
      }
    }
    """

    query_cn_recent = """
    query recentSubmissions($userSlug: String!) {
      recentSubmissions(userSlug: $userSlug) {
        status
        submitTime
        question {
          questionFrontendId
          difficulty
        }
      }
    }
    """
    
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

    result = {
        "total_ac": 0,
        "new_solved": [] # List of {id, diff}
    }

    try:
        if region == 'US':
            # 1. Total AC
            resp = requests.post(LEETCODE_COM_URL, json={'query': query_com, 'variables': {"username": username}}, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('matchedUser'):
                    stats = data['data']['matchedUser']['submitStats']['acSubmissionNum']
                    result["total_ac"] = next(item['count'] for item in stats if item['difficulty'] == 'All')

            # 2. Recent Submissions
            resp_recent = requests.post(LEETCODE_COM_URL, json={'query': query_com_recent, 'variables': {"username": username}}, headers=headers, timeout=10)
            if resp_recent.status_code == 200:
                data = resp_recent.json()
                if data.get('data') and data['data'].get('recentAcSubmissionList'):
                    for sub in data['data']['recentAcSubmissionList']:
                        if int(sub['timestamp']) >= start_ts:
                            # US API doesn't give difficulty in this query, defaulting to Unknown or skipping diff logic
                            result["new_solved"].append({
                                "id": sub['title'], # Using title as ID for US since slug/id missing in simple query
                                "diff": "Unknown" 
                            })

        elif region == 'CN':
            # 1. Total AC
            resp = requests.post(LEETCODE_CN_URL, json={'query': query_cn_stats, 'variables': {"userSlug": username}}, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and data['data'].get('userProfileUserQuestionProgress'):
                    stats = data['data']['userProfileUserQuestionProgress']['numAcceptedQuestions']
                    result["total_ac"] = sum(item['count'] for item in stats)

            # 2. Recent Submissions
            resp_recent = requests.post(LEETCODE_CN_URL, json={'query': query_cn_recent, 'variables': {"userSlug": username}}, headers=headers, timeout=10)
            if resp_recent.status_code == 200:
                data = resp_recent.json()
                if data.get('data') and data['data'].get('recentSubmissions'):
                    for sub in data['data']['recentSubmissions']:
                        if sub['status'] == 'A_10' and sub['submitTime'] >= start_ts:
                            result["new_solved"].append({
                                "id": sub['question']['questionFrontendId'],
                                "diff": sub['question']['difficulty']
                            })

    except Exception as e:
        print(f"Error fetching {username}: {e}")
        return None

    return result

def main():
    with open('data/users.json', 'r') as f:
        user_list = json.load(f)

    stats_file = 'data/stats.json'
    if os.path.exists(stats_file):
        with open(stats_file, 'r') as f:
            all_stats = json.load(f)
    else:
        all_stats = {}

    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    current_iso_week = datetime.now(timezone.utc).isocalendar()[1]

    for entry in user_list:
        if isinstance(entry, dict):
            username = entry.get("username")
            region = entry.get("region", "CN")
        else:
            username = entry
            region = "CN"

        fetched = get_recent_submissions(username, region)
        if not fetched:
            continue

        if username not in all_stats:
            all_stats[username] = {
                "week": current_iso_week,
                "history": [],
                "solved_problems": {} # {id: diff}
            }

        # Check for new week -> Archive & Reset
        if all_stats[username].get("week") != current_iso_week:
            # Archive
            prev_solved = len(all_stats[username].get("solved_problems", {}))
            if prev_solved > 0:
                all_stats[username]["history"].append({
                    "week": all_stats[username]["week"],
                    "year": datetime.now().year,
                    "solved": prev_solved
                })
            
            # Reset
            all_stats[username]["week"] = current_iso_week
            all_stats[username]["solved_problems"] = {}
        
        # Ensure solved_problems dict exists (for old schema compatibility)
        if "solved_problems" not in all_stats[username]:
             all_stats[username]["solved_problems"] = {}

        # Merge new submissions
        for problem in fetched["new_solved"]:
            p_id = problem["id"]
            p_diff = problem["diff"]
            all_stats[username]["solved_problems"][p_id] = p_diff

        # Calculate Stats
        solved_problems = all_stats[username]["solved_problems"]
        week_solved = len(solved_problems)
        
        breakdown = {"Easy": 0, "Medium": 0, "Hard": 0}
        for diff in solved_problems.values():
            if diff in breakdown:
                breakdown[diff] += 1
        
        # Update State
        all_stats[username]["current"] = fetched["total_ac"]
        all_stats[username]["last_updated"] = today_str
        all_stats[username]["week_solved"] = week_solved
        all_stats[username]["week_breakdown"] = breakdown
        # We don't need 'baseline' anymore with this logic, but keeping it won't hurt.

    with open(stats_file, 'w') as f:
        json.dump(all_stats, f, indent=2)

if __name__ == "__main__":
    main()