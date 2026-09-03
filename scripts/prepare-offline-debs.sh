#!/usr/bin/env sh
set -eu

output_dir=${1:-memProject/offline-debs}
platform=${2:-amd64}
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
case "$output_dir" in
    /*) ;;
    *) output_dir="$project_root/$output_dir" ;;
esac
mkdir -p "$output_dir"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)

rm -f "$output_dir"/*.deb
mkdir -p "$output_dir/partial"

echo "Downloading Debian packages for linux/$platform into $output_dir"
docker run --rm --platform "linux/$platform" \
    -v "$output_dir:/out" \
    debian:bookworm-slim \
    sh -euxc '
        apt-get update
        apt-get --download-only --no-install-recommends -y \
            -o Dir::Cache::archives=/out \
            install build-essential libpq-dev curl
        rm -rf /out/partial
    '

package_count=$(find "$output_dir" -maxdepth 1 -name '*.deb' -type f | wc -l)
test "$package_count" -gt 0
echo "Downloaded $package_count Debian packages. Copy memProject/offline-debs with the source tree."