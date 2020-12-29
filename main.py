import requests
import json
import arxiv
import time
import os
import sys
from dotenv import load_dotenv

HEADERS = {'content-type': 'application/json'}

config = None


class Config:
    def __init__(self):
        load_dotenv()
        self.gcsURL = self.loadOr('APP_GCS_URL')
        self.maxResult = self.loadInt('APP_MAX_RESULT', 10)
        self.category = self.loadOr('APP_CATEGORY', "cat:cs.AI")
        self.slackURL = self.loadOr('APP_SLACK_URL')

        if (self.gcsURL == "" or self.slackURL == ""):
            print("GCS_URL or SLACK_URL must be set")
            sys.exit(1)

    def loadOr(self, key, default=""):
        v = os.getenv(key)
        if (v == "" or v is None):
            return default
        return v

    def loadInt(self, key, default):
        v = os.getenv(key)
        if (v == "" or v is None):
            return default
        try:
            return int(v)
        except Exception as e:
            print("parse int error")
            return default


def ping():
    res = requests.get(config.gcsURL, headers=HEADERS, allow_redirects=True)
    print(res.text)


def gasTranslate(payload):
    """
    gasにリクエストを送り翻訳

    Parameters
    ----------
    payload : dict
    title, summaryをキーに含むdict

    """
    try:
        res = requests.post(config.gcsURL, data=json.dumps(
            payload), headers=HEADERS, timeout=(20, 20))
        if (res.status_code != 200):
            print("gas request error, code: {}, message:{}".format(
                res.status_code, res.text))
            return None
        return res.text
    except Exception as e:
        print("gas request exception")
        print(e)
        return None


class TranslateData:
    def __init__(self, title, summary):
        self.title = title
        self.summary = summary

    def toDict(self):
        return {
            'title_en': self.title,
            'summary_en': self.summary
        }


def parseGCSResult(gcsResult):
    res = json.loads(gcsResult)
    if ('data' not in res):
        print('key: data is not exist')
        return None

    data = res['data']
    if ('title_en' not in data or 'summary_en' not in data):
        print('key: title_en or summary_en is not exist')
        return None
    return TranslateData(data['title_en'], data['summary_en'])


def getArXiv():
    try:
        res = arxiv.query(query=config.category, max_results=config.maxResult,
                          sort_by='submittedDate')
        return res
    except Exception as e:
        print("getArXiv error")
        print(e)
        return None


class ArxivData:
    def __init__(self, title, author, summary, arxiv_url, published):
        self.title = title
        self.author = author
        self.summary = summary
        self.arxiv_url = arxiv_url
        self.published = published

    def toDict(self):
        return {
            'title': self.title,
            'author': self.author,
            'summary': self.summary,
            'arxiv_url': self.arxiv_url,
            'published': self.published,
        }


def parseArXivResults(arxiv_result):
    arr = []
    for v in arxiv_result:
        if (
            "title" in v and
            "author" in v and
            "summary" in v and
            "arxiv_url" in v and
                "published" in v):

            arr.append(
                ArxivData(
                    v["title"],
                    v["author"],
                    v["summary"].replace("\n", ""),
                    v["arxiv_url"],
                    v["published"]
                ))
    return arr


def sendSlack(arxivData, translateData):
    tmp = []
    for v in arxivData.summary.split("\n"):
        tmp.append("> {}".format(v))
    summary_with_quate = "\n".join(tmp)

    textList = [
        "*{}*".format(translateData.title),
        "> {}".format(arxivData.title),
        "_authors: {} (submitted {})_".format(
            arxivData.author, arxivData.published),
        "\n",
        "{}".format(translateData.summary),
        "{}".format(summary_with_quate),
        "{}".format(arxivData.arxiv_url)
    ]
    payload = {"text": "\n".join(textList)}

    try:
        requests.post(config.slackURL, data=json.dumps(payload),
                      headers=HEADERS, timeout=(20, 20))
        print("send slack success")
    except Exception as e:
        print("send slack error")
        print(e)


def main():
    global config
    config = Config()

    res = getArXiv()
    if (res is None):
        print("get arxiv failed")
        sys.exit(1)

    arxivDataList = parseArXivResults(res)
    for arxivData in arxivDataList:
        res = gasTranslate(arxivData.toDict())
        if (res is None):
            continue
        translateData = parseGCSResult(res)
        if (translateData is None):
            continue

        sendSlack(arxivData, translateData)
        time.sleep(10)


if __name__ == "__main__":
    main()
