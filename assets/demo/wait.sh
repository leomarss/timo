# Wait for a fresh 30-second code window, so the recorded codes show plenty of time left.
sleep $(( 30 - $(date +%s) % 30 ))
echo READY
