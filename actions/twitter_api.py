"""SONIC AI — Twitter/X API Integration

Full Twitter/X control via API v2 (OAuth 2.0).
Features:
- Post tweets
- Search tweets
- View/manage timeline
- Like, retweet, reply
- View profile info
- Monitor mentions
- Trending topics

Setup:
    Set these in config/api_keys.json:
    {
        "twitter_api_key": "...",
        "twitter_api_secret": "...",
        "twitter_access_token": "...",
        "twitter_access_secret": "...",
        "twitter_bearer_token": "..."
    }

Usage:
    "Twitter pe tweet karo: Hello World"
    "Twitter search karo Python"
    "Mere mentions dikhao"
    "Trending topics dikhao"
"""
from __future__ import annotations

import json
import time
import hashlib
import hmac
import base64
import urllib.parse
import logging
from pathlib import Path
from typing import Any
import requests

logger = logging.getLogger("TWITTER_API")

# ── Config ──────────────────────────────────────────────────────────────
_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
_TWITTER_BASE = ""  # Loaded from config
_TWITTER_11 = ""  # Loaded from config


def _load_credentials() -> dict:
    """Load Twitter API credentials from config."""
    global _TWITTER_BASE, _TWITTER_11
    if not _CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        _TWITTER_BASE = data.get("twitter_api_base", "https://api.twitter.com/2")
        _TWITTER_11 = data.get("twitter_api_base_v11", "https://api.twitter.com/1.1")
        return {
            "api_key": data.get("twitter_api_key", ""),
            "api_secret": data.get("twitter_api_secret", ""),
            "access_token": data.get("twitter_access_token", ""),
            "access_secret": data.get("twitter_access_secret", ""),
            "bearer_token": data.get("twitter_bearer_token", ""),
        }
    except Exception:
        return {}


def _save_credentials(creds: dict) -> None:
    """Save Twitter API credentials to config."""
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
    else:
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data.update({
        "twitter_api_key": creds.get("api_key", ""),
        "twitter_api_secret": creds.get("api_secret", ""),
        "twitter_access_token": creds.get("access_token", ""),
        "twitter_access_secret": creds.get("access_secret", ""),
        "twitter_bearer_token": creds.get("bearer_token", ""),
        "twitter_api_base": creds.get("api_base", "https://api.twitter.com/2"),
        "twitter_api_base_v11": creds.get("api_base_v11", "https://api.twitter.com/1.1"),
    })

    _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── OAuth 1.0a Signature ────────────────────────────────────────────────

def _oauth_sign(method: str, url: str, params: dict, creds: dict) -> dict:
    """Generate OAuth 1.0a signature."""
    oauth_params = {
        "oauth_consumer_key": creds["api_key"],
        "oauth_nonce": hashlib.md5(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["access_token"],
        "oauth_version": "1.0",
    }

    all_params = {**params, **oauth_params}
    sorted_params = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in sorted(all_params.items()))
    base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"
    signing_key = f"{urllib.parse.quote(creds['api_secret'], safe='')}&{urllib.parse.quote(creds['access_secret'], safe='')}"
    signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()
    oauth_params["oauth_signature"] = signature
    return oauth_params


def _bearer_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
    """Make a Bearer token request (for v2 API)."""
    creds = _load_credentials()
    if not creds.get("bearer_token"):
        return {"error": "Twitter bearer token not configured. Set twitter_bearer_token in config/api_keys.json"}

    headers = {"Authorization": f"Bearer {creds['bearer_token']}"}
    url = f"{_TWITTER_BASE}{endpoint}"

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            resp = requests.post(url, headers=headers, json=json_data, timeout=15)
        else:
            return {"error": f"Unsupported method: {method}"}

        if resp.status_code >= 400:
            return {"error": f"API error {resp.status_code}: {resp.text[:200]}"}

        return resp.json() if resp.text else {"success": True}

    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {e}"}


def _oauth1_request(method: str, endpoint: str, params: dict = None, json_data: dict = None) -> dict:
    """Make an OAuth 1.0a request (for v1.1 API)."""
    creds = _load_credentials()
    if not creds.get("api_key"):
        return {"error": "Twitter API credentials not configured. Set twitter_api_key in config/api_keys.json"}

    url = f"{_TWITTER_11}{endpoint}"
    oauth_params = _oauth_sign(method, url, params or {}, creds)

    headers = {
        "Authorization": "OAuth " + ", ".join(
            f'{k}="{urllib.parse.quote(str(v), safe="")}"'
            for k, v in sorted(oauth_params.items())
        )
    }

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        elif method == "POST":
            resp = requests.post(url, headers=headers, data=params or json_data, timeout=15)
        else:
            return {"error": f"Unsupported method: {method}"}

        if resp.status_code >= 400:
            return {"error": f"API error {resp.status_code}: {resp.text[:200]}"}

        return resp.json() if resp.text else {"success": True}

    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {e}"}


# ── Twitter Operations ──────────────────────────────────────────────────

def _post_tweet(text: str, reply_to: str = None) -> dict:
    """Post a tweet."""
    data = {"text": text}
    if reply_to:
        data["reply"] = {"in_reply_to_tweet_id": reply_to}
    return _bearer_request("POST", "/tweets", json_data=data)


def _search_tweets(query: str, limit: int = 10) -> dict:
    """Search recent tweets."""
    params = {
        "query": query,
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "name,username",
    }
    return _bearer_request("GET", "/tweets/search/recent", params=params)


def _get_mentions(limit: int = 10) -> dict:
    """Get mentions of the authenticated user."""
    # First get user ID
    me = _bearer_request("GET", "/users/me")
    if "error" in me:
        return me

    user_id = me.get("data", {}).get("id")
    if not user_id:
        return {"error": "Could not get user ID"}

    params = {
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics",
        "expansions": "author_id",
        "user.fields": "name,username",
    }
    return _bearer_request("GET", f"/users/{user_id}/mentions", params=params)


def _get_timeline(limit: int = 10) -> dict:
    """Get user's home timeline."""
    me = _bearer_request("GET", "/users/me")
    if "error" in me:
        return me

    user_id = me.get("data", {}).get("id")
    if not user_id:
        return {"error": "Could not get user ID"}

    params = {
        "max_results": min(limit, 100),
        "tweet.fields": "created_at,public_metrics",
        "expansions": "author_id",
        "user.fields": "name,username",
    }
    return _bearer_request("GET", f"/users/{user_id}/timelines/reverse_chronological", params=params)


def _like_tweet(tweet_id: str) -> dict:
    """Like a tweet."""
    me = _bearer_request("GET", "/users/me")
    if "error" in me:
        return me
    user_id = me.get("data", {}).get("id")
    return _bearer_request("POST", f"/users/{user_id}/likes", json_data={"tweet_id": tweet_id})


def _retweet(tweet_id: str) -> dict:
    """Retweet a tweet."""
    me = _bearer_request("GET", "/users/me")
    if "error" in me:
        return me
    user_id = me.get("data", {}).get("id")
    return _bearer_request("POST", f"/users/{user_id}/retweets", json_data={"tweet_id": tweet_id})


def _reply(tweet_id: str, text: str) -> dict:
    """Reply to a tweet."""
    return _post_tweet(text, reply_to=tweet_id)


def _get_trending() -> dict:
    """Get trending topics (requires location - defaults to worldwide)."""
    # Twitter v2 trends endpoint is limited, use v1.1
    return _oauth1_request("GET", "/trends/place.json", {"id": "1"})  # 1 = worldwide


def _get_profile(username: str) -> dict:
    """Get user profile info."""
    params = {
        "user.fields": "created_at,description,public_metrics,profile_image_url",
    }
    return _bearer_request("GET", f"/users/by/username/{username}", params=params)


def _delete_tweet(tweet_id: str) -> dict:
    """Delete a tweet."""
    me = _bearer_request("GET", "/users/me")
    if "error" in me:
        return me
    user_id = me.get("data", {}).get("id")
    return _bearer_request("DELETE", f"/users/{user_id}/tweets/{tweet_id}")


def _setup_credentials(api_key: str, api_secret: str, access_token: str, access_secret: str, bearer_token: str, api_base: str = "", api_base_v11: str = "") -> dict:
    """Save Twitter API credentials."""
    creds = {
        "api_key": api_key,
        "api_secret": api_secret,
        "access_token": access_token,
        "access_secret": access_secret,
        "bearer_token": bearer_token,
        "api_base": api_base,
        "api_base_v11": api_base_v11,
    }
    _save_credentials(creds)
    return {"success": True, "message": "Twitter credentials saved"}


# ── Tool Interface ──────────────────────────────────────────────────────

def twitter_api(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Twitter/X integration tool.
    Full Twitter control via API.
    """
    action = parameters.get("action", "timeline")

    # ── Setup ──
    if action == "setup":
        result = _setup_credentials(
            parameters.get("api_key", ""),
            parameters.get("api_secret", ""),
            parameters.get("access_token", ""),
            parameters.get("access_secret", ""),
            parameters.get("bearer_token", ""),
            parameters.get("api_base", ""),
            parameters.get("api_base_v11", ""),
        )
        return "Twitter credentials saved!" if result.get("success") else result.get("error", "Setup failed")

    # ── Check credentials ──
    creds = _load_credentials()
    if not creds.get("bearer_token"):
        return "Twitter not configured. Run: twitter_api(action='setup', api_key='...', api_secret='...', access_token='...', access_secret='...', bearer_token='...')"

    # ── Tweet Actions ──
    if action == "tweet":
        text = parameters.get("text", "")
        if not text:
            return "Error: text is required"
        result = _post_tweet(text)
        if "data" in result:
            return f"Tweet posted! ID: {result['data']['id']}"
        return f"Error: {result.get('error', 'Unknown error')}"

    elif action == "reply":
        tweet_id = parameters.get("tweet_id", "")
        text = parameters.get("text", "")
        if not tweet_id or not text:
            return "Error: tweet_id and text are required"
        result = _reply(tweet_id, text)
        if "data" in result:
            return f"Reply posted! ID: {result['data']['id']}"
        return f"Error: {result.get('error', 'Unknown error')}"

    elif action == "delete":
        tweet_id = parameters.get("tweet_id", "")
        if not tweet_id:
            return "Error: tweet_id is required"
        result = _delete_tweet(tweet_id)
        if "success" in result or "data" in result:
            return "Tweet deleted!"
        return f"Error: {result.get('error', 'Unknown error')}"

    # ── Search ──
    elif action == "search":
        query = parameters.get("query", "")
        if not query:
            return "Error: query is required"
        limit = parameters.get("limit", 10)
        result = _search_tweets(query, limit)
        if "data" in result:
            tweets = result["data"]
            lines = [f"Search Results ({len(tweets)}):"]
            for t in tweets:
                metrics = t.get("public_metrics", {})
                lines.append(f"  [{t.get('created_at', '')[:10]}] {t['text'][:100]}... (RT: {metrics.get('retweet_count', 0)}, Likes: {metrics.get('like_count', 0)})")
            return "\n".join(lines)
        return f"No results or error: {result.get('error', '')}"

    # ── Timeline ──
    elif action == "timeline":
        limit = parameters.get("limit", 10)
        result = _get_timeline(limit)
        if "data" in result:
            tweets = result.get("data", [])
            lines = [f"Timeline ({len(tweets)} tweets):"]
            for t in tweets:
                lines.append(f"  @{t.get('author', {}).get('username', '?')}: {t['text'][:100]}...")
            return "\n".join(lines)
        return f"Error: {result.get('error', 'Could not get timeline')}"

    # ── Mentions ──
    elif action == "mentions":
        limit = parameters.get("limit", 10)
        result = _get_mentions(limit)
        if "data" in result:
            tweets = result["data"]
            lines = [f"Mentions ({len(tweets)}):"]
            for t in tweets:
                lines.append(f"  @{t.get('author', {}).get('username', '?')}: {t['text'][:100]}")
            return "\n".join(lines)
        return f"Error: {result.get('error', 'Could not get mentions')}"

    # ── Interactions ──
    elif action == "like":
        tweet_id = parameters.get("tweet_id", "")
        if not tweet_id:
            return "Error: tweet_id is required"
        result = _like_tweet(tweet_id)
        if "data" in result or "success" in result:
            return "Tweet liked!"
        return f"Error: {result.get('error', 'Unknown error')}"

    elif action == "retweet":
        tweet_id = parameters.get("tweet_id", "")
        if not tweet_id:
            return "Error: tweet_id is required"
        result = _retweet(tweet_id)
        if "data" in result or "success" in result:
            return "Retweeted!"
        return f"Error: {result.get('error', 'Unknown error')}"

    # ── Trending ──
    elif action == "trending":
        result = _get_trending()
        if isinstance(result, list) and len(result) > 0:
            trends = result[0].get("trends", [])
            lines = [f"Trending Topics ({len(trends)}):"]
            for t in trends[:20]:
                lines.append(f"  {t['name']} - {t.get('tweet_volume', 'N/A')} tweets")
            return "\n".join(lines)
        return f"Error: {result.get('error', 'Could not get trends')}"

    # ── Profile ──
    elif action == "profile":
        username = parameters.get("username", "")
        if not username:
            # Get own profile
            result = _bearer_request("GET", "/users/me", {"user.fields": "created_at,description,public_metrics,profile_image_url"})
        else:
            result = _get_profile(username)
        if "data" in result:
            u = result["data"]
            metrics = u.get("public_metrics", {})
            return (
                f"@{u['username']} ({u['name']})\n"
                f"Bio: {u.get('description', 'N/A')}\n"
                f"Followers: {metrics.get('followers_count', 0)}\n"
                f"Following: {metrics.get('following_count', 0)}\n"
                f"Tweets: {metrics.get('tweet_count', 0)}\n"
                f"Joined: {u.get('created_at', 'N/A')[:10]}"
            )
        return f"Error: {result.get('error', 'User not found')}"

    return f"Unknown action: {action}. Use: setup, tweet, reply, delete, search, timeline, mentions, like, retweet, trending, profile"
