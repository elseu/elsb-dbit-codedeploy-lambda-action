FROM amazon/aws-cli

RUN yum install -y jq

COPY deploy.sh /deploy.sh
RUN chmod +x /deploy.sh

ENTRYPOINT [ "/deploy.sh" ]