#!/bin/bash
export DATABASE_URL="postgresql://rduser:rd_pass_2026@10.43.20.233:5432/robotdefense"
export KEYWORDS="robot hacked,robot attack,robot security,AI robot threat,robot vulnerability"
python3 /opt/robotdefense/crawler/crawler.py >> /var/log/robot-news-crawler.log 2>&1
