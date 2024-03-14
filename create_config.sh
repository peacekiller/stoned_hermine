#!/bin/sh

echo "dong"

check_env() {
  env_val=$(printenv "$1")
  echo "$env_val"
  if [ -z "$env_val" ]; then
    echo "Container failed to start, pls pass -e $1"
    exit 1
  fi
}

check_env "STEIN_APP_USERNAME"
check_env "STEIN_APP_PASSWORD"
check_env "STEIN_APP_ORGANISATION"
check_env "HERMINE_USERNAME"
check_env "HERMINE_PASSWORD"
check_env "HERMINE_ENCRYPTION_KEY"
check_env "HERMINE_CHANNEL_ID"

