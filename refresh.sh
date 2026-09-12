#!/bin/bash
# Scrape, regenerate the page, and commit it so the cloud routine can publish it.
# The cloud sandbox proxy blocks every car portal, so scraping has to happen here.
set -u
cd "$(dirname "$0")" || exit 1
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"

/usr/bin/python3 carhunt.py --html || { echo "carhunt failed"; exit 1; }

# refuse to commit a page the sanity checks would reject downstream
bytes=$(wc -c < deals.html)
rows=$(grep -c 'class="row"' deals.html || true)
if [ "$bytes" -lt 20000 ] || [ "$rows" -lt 1 ]; then
  echo "page failed sanity check (${bytes} bytes, ${rows} rows) - not committing"
  exit 1
fi

# stage first: git diff reports nothing for a file that is not tracked yet
git add deals.html
if ! git diff --cached --quiet -- deals.html; then
  git -c user.email=ranjith.chowdary@gmail.com -c user.name=ranpold \
      commit -q -m "Refresh listings $(date '+%Y-%m-%d %H:%M')"
  git push -q org main && echo "pushed refreshed page (${rows} rows)"
else
  echo "page unchanged - nothing to push"
fi
