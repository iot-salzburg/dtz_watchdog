#!/usr/bin/env bash
echo "Printing 'docker service ls | grep watchdog':"
docker service ls | grep watchdog
echo ""
echo "Printing 'docker stack ps watchdog':"
docker stack ps watchdog
