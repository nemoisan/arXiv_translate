import requests
import json
import arxiv
import time
import os
import sys
from dotenv import load_dotenv

HEADERS = {'content-type': 'application/json'}

config = None
SAVE_FILE = "./save.log"


class Config:
    def __init__(self):
        load_dotenv()
        self.gasURL = self.loadOr(
            'APP_GAS_URL', "https://script.google.com/macros/s/AKfycbwD9QatQCX0z5tiVKhGshhN0HbP_1eTm4dy_exeMkTJ_jqvURb-bNe8xg/exec")
        self.maxResult = self.loadInt('APP_MAX_RESULT', 10)
        self.category = self.loadOr('APP_CATEGORY', "cat:cs.AI")
        self.slackURL = self.loadOr('APP_SLACK_URL')

        if (self.gasURL == "" or self.slackURL == ""):
            print("GAS_URL or SLACK_URL must be set")
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
    res = requests.get(config.gasURL, headers=HEADERS, allow_redirects=True)
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
        res = requests.post(config.gasURL, data=json.dumps(
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


def parseGASResult(gasResult):
    res = json.loads(gasResult)
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
        # res = arxiv.query(query=config.category, max_results=config.maxResult,
        #                   sort_by='submittedDate')
        res = arxiv.Search(
            config.category,
            max_results=config.maxResult,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        return res
    except Exception as e:
        print("getArXiv error")
        print(e)
        return None


def arXivResultsToDict(arxivResult):
    authors = [a.name for a in arxivResult.authors]
    return {
        "title": arxivResult.title.replace("\n", ""),
        "authors": authors,
        "summary": arxivResult.summary.replace("\n", "")
    }


def sendSlack(arxivData, translateData):
    tmp = []
    for v in arxivData.summary.split("\n"):
        tmp.append("> {}".format(v))
    summary_with_quate = "\n".join(tmp)

    if len(arxivData.links) > 0:
        arxiv_url = arxivData.links[0]

    textList = [
        "*{}*".format(translateData.title),
        "> {}".format(arxivData.title),
        "_authors: {} (submitted {})_".format(
            arxivData.authors, arxivData.published),
        "\n",
        "{}".format(translateData.summary),
        "{}".format(summary_with_quate),
        "{}".format(arxiv_url)
    ]
    payload = {"text": "\n".join(textList)}

    try:
        requests.post(config.slackURL, data=json.dumps(payload),
                      headers=HEADERS, timeout=(20, 20))
        print("send slack success")
    except Exception as e:
        print("send slack error")
        print(e)


def logsResults(arxivData):
    ids = []
    for v in arxivData.results():
        ids.append(v.entry_id)

    with open(SAVE_FILE, "w") as f:
        f.write("\n".join(ids))


def getNotExitDataFromLog(arxivData):
    if (not os.path.exists(SAVE_FILE)):
        return arxivData.results()

    with open(SAVE_FILE, "r") as f:
        l = [s.strip() for s in f.readlines()]

    n = []
    for v in arxivData.results():
        if(v.entry_id not in l):
            n.append(v)
    return n


def main():
    global config
    config = Config()

    arxivDataRaw = getArXiv()
    if (arxivDataRaw is None):
        print("get arxiv failed")
        sys.exit(1)
    arxivDataList = getNotExitDataFromLog(arxivDataRaw)
    logsResults(arxivDataRaw)

    for arxivData in arxivDataList:
        arxivDataDict = arXivResultsToDict(arxivData)
        print("hoge", arxivDataDict)
        res = gasTranslate(arxivDataDict)
        if (res is None):
            continue
        translateData = parseGASResult(res)
        if (translateData is None):
            continue

        sendSlack(arxivData, translateData)
        time.sleep(10)


if __name__ == "__main__":
    main()
