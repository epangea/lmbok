# FreqLearn — show current sessions.language distribution after the bad backfill
# Run on server:  bash scripts/show_lang_distribution.sh

set -e

mysql freqlearn -e "
SELECT IFNULL(language, '(null)') AS language, COUNT(*) AS n
FROM sessions
GROUP BY language
ORDER BY n DESC;
"