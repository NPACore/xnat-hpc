#!/usr/bin/env bash
#
# find all recent sessions
# use datequery.xml for >= DATE_CUTOFF_TEMPLATE_REPLACE
#
# ./misc/query.bash | jq '.ResultSet.Result[]|[.project, .session_id, .insert_date]|@tsv' -r
#
# 20260705WF - init
#
cd "$(dirname "$0")"
creds="npac:$(pass work/xnat-npac)"
xnathost=https://xnat.mrrc.upmc.edu
cutoff=$(date -d '3 day ago' +%F)

## get avaliable options
# https://wiki.xnat.org/xnat-api/how-to-query-the-xnat-search-engine-with-rest-api
test -r query_options.txt ||
   curl -u "$creds" $xnathost/data/search/elements?format=csv > "$_"
test -r query_mr_options.txt ||
   curl -u "$creds" $xnathost/data/search/elements/xnat:mrSessionData?format=csv > "$_"

# put current cutoff into file (as pipe) and POST to search
# don't want to hard code date in xml query. query is annoying long to put here and might be useful for other scripts.
# pipe so we don't have extra files hanging around
sed "s/DATE_CUTOFF_TEMPLATE_REPLACE/$cutoff/g" datequery.xml |
 curl -s -u "$creds" \
  -X POST \
  "$xnathost/data/search?format=json"  \
  --data-binary @-  
