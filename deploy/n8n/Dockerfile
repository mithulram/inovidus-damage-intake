# n8n for the hosted demo (Render, free web service). Imports and publishes the committed
# workflow on every start (the free plan has no persistent disk) and creates the owner
# account from secrets on a private port BEFORE the public port opens (no unclaimed setup page).
FROM n8nio/n8n:2.48.5
COPY workflows/n8n_schadenmeldung.json /opt/intake/workflow.json
COPY deploy/n8n/configure.mjs deploy/n8n/start.sh /opt/intake/
USER root
RUN chmod +x /opt/intake/start.sh
USER node
ENTRYPOINT ["/bin/sh", "/opt/intake/start.sh"]
