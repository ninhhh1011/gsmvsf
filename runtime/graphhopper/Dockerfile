FROM eclipse-temurin:21.0.8_9-jre-jammy@sha256:db1689535962d757a5adabf57387584ed543d38c0b9d1fe870123ea362ad73b0
WORKDIR /opt/graphhopper
ADD --checksum=sha256:b59c024afe172ec6ec85b6327006c3138ec58c7d0bcd26253d0e42853f613def https://repo.maven.apache.org/maven2/com/graphhopper/graphhopper-web/11.0/graphhopper-web-11.0.jar graphhopper.jar
COPY config.yml ./config.yml
COPY custom_models/hanoi_motorcycle.json ./custom_models/hanoi_motorcycle.json
EXPOSE 8989
ENTRYPOINT ["java", "-Xmx2g", "-jar", "graphhopper.jar", "server", "config.yml"]
