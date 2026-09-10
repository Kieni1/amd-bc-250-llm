#!/usr/bin/env bash
# Locate a tarball in $HOME and the matching extracted evidence directory under
# $HOME/bc250-quality. This fixes the earlier mistaken assumption that the
# extracted evidence directory lives beside the tarball.
set -Eeuo pipefail

PATTERN="${1:-batch*.tar.gz}"
TAR="$(find "$HOME" -maxdepth 1 -type f -name "$PATTERN" -printf '%T@ %p\n' \
    | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$TAR" ]] || { echo "No tarball matched: $PATTERN" >&2; exit 1; }
NAME="$(basename "${TAR%.tar.gz}")"
DIR="${BC250_QUALITY_ROOT:-$HOME/bc250-quality}/$NAME"

printf 'Tarball:     %s\n' "$TAR"
printf 'Evidence dir: %s\n' "$DIR"
[[ -d "$DIR" ]] || { echo 'Evidence directory not found.' >&2; exit 2; }

for file in post/restoration-status.txt aggregate.txt post/credential-scan.txt; do
    if [[ -f "$DIR/$file" ]]; then
        printf '\n--- %s ---\n' "$file"
        cat "$DIR/$file"
    fi
done

printf '\n--- serious warnings ---\n'
if [[ -s "$DIR/post/serious-warnings.txt" ]]; then
    cat "$DIR/post/serious-warnings.txt"
elif [[ -f "$DIR/post/serious-warnings.txt" ]]; then
    echo 'No matched OOM/GPU/device-loss warnings.'
else
    echo 'No serious-warnings.txt in this batch.'
fi

printf '\n--- archive SHA256 ---\n'
sha256sum "$TAR"
