FROM amazon/aws-cli

COPY deploy.sh /deploy.sh
RUN chmod +x /deploy.sh

ENTRYPOINT [ "/deploy.sh" ]