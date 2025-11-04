#!/usr/bin/env bash

date="$(TZ="UTC" date +%Y-%m-%dT%H-%M-%SZ)"

target_dir="$HOME/svalbard_radar_backups/"

if ! [[ -d "$target_dir" ]]; then
  mkdir -p "$target_dir"
fi

zip -r9 "$target_dir/svalbard_radar_backup_$date.zip" submitted/

echo -e "\nSaved to $target_dir"
