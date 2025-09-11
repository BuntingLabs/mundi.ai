# tippecanoe
FROM node:20-bookworm-slim AS tippecanoe-builder
ARG TIPPECANOE_TAG=2.77.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential libsqlite3-dev zlib1g-dev  ca-certificates \
    && git clone --depth 1 --branch ${TIPPECANOE_TAG} https://github.com/felt/tippecanoe /tmp/tippecanoe \
    && make -C /tmp/tippecanoe -j$(nproc) && make -C /tmp/tippecanoe install \
    && rm -rf /tmp/tippecanoe \
    && apt-get purge -y git build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# build gdal from source to get version later than what debian offers
FROM node:20-bookworm-slim AS gdal-builder
ARG GDAL_VERSION=3.11.3
WORKDIR /tmp

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates wget \
        swig \
        libproj-dev proj-data proj-bin \
        libsqlite3-dev libexpat1-dev libcurl4-openssl-dev \
        zlib1g-dev libtiff-dev libgeotiff-dev libpng-dev libjpeg-dev \
        python3-dev python3-numpy python3-setuptools \
        libpq-dev \
        libgeos-dev \
    && rm -rf /var/lib/apt/lists/* \
    && wget https://github.com/OSGeo/gdal/releases/download/v${GDAL_VERSION}/gdal-${GDAL_VERSION}.tar.gz \
    && tar -xzf gdal-${GDAL_VERSION}.tar.gz \
    && cd gdal-${GDAL_VERSION} \
    && mkdir build && cd build \
    && cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_PYTHON_BINDINGS=ON \
        -DBUILD_APPS=ON \
        -DGDAL_BUILD_OPTIONAL_DRIVERS=ON \
        -DOGR_BUILD_OPTIONAL_DRIVERS=ON \
        -DGDAL_USE_POSTGRESQL=ON \
    && cmake --build . -j$(nproc) \
    && cmake --build . --target install \
    && ldconfig \
    && rm -rf /tmp/gdal-${GDAL_VERSION}*

# maplibre
FROM node:20-bookworm-slim AS maplibre-builder
ARG MAPLIBRE_TAG=node-v6.1.0
WORKDIR /opt
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && git clone --depth 1 --recursive --branch ${MAPLIBRE_TAG} \
        https://github.com/maplibre/maplibre-native.git \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/maplibre-native/platform/node
RUN npm ci && npm pack --silent

# base runtime
FROM node:20-bookworm-slim AS base
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2-dev libgles2-mesa-dev libgbm-dev \
        libuv1-dev libprotobuf-dev xserver-xorg-core xvfb x11-utils dbus xauth \
        python3-apt python3 \
        proj-bin libproj-dev libproj25 proj-data \
        libsqlite3-0 libexpat1 libcurl4 \
        zlib1g libtiff6 libgeotiff5 libpng16-16 libjpeg62-turbo \
        libpq5 \
        libgeos-c1v5 \
    && rm -rf /var/lib/apt/lists/*

# fetch GDAL stuff from builder
COPY --from=gdal-builder /usr/local/bin/gdal* /usr/local/bin/
COPY --from=gdal-builder /usr/local/bin/ogr* /usr/local/bin/
COPY --from=gdal-builder /usr/local/bin/nearblack /usr/local/bin/
COPY --from=gdal-builder /usr/local/bin/gdaldem /usr/local/bin/
COPY --from=gdal-builder /usr/local/lib/libgdal* /usr/local/lib/
COPY --from=gdal-builder /usr/local/lib/gdalplugins /usr/local/lib/gdalplugins
COPY --from=gdal-builder /usr/local/lib/python3*/dist-packages/osgeo /usr/local/lib/python3.11/dist-packages/osgeo
COPY --from=gdal-builder /usr/local/share/gdal /usr/local/share/gdal
RUN ldconfig

COPY --from=tippecanoe-builder /usr/local/bin/tippecanoe* /usr/local/bin/

# tools / deps
FROM base AS tools
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y --no-install-recommends wget libpng-dev ca-certificates \
    && npm install -g @maplibre/maplibre-gl-style-spec \
    && wget -qO /tmp/pmtiles.tar.gz \
         https://github.com/protomaps/go-pmtiles/releases/download/v1.25.3/go-pmtiles_1.25.3_Linux_x86_64.tar.gz \
    && tar -xzf /tmp/pmtiles.tar.gz -C /usr/local/bin && chmod +x /usr/local/bin/pmtiles \
    && rm /tmp/pmtiles.tar.gz

# python/uv
FROM tools AS python-builder
COPY --from=ghcr.io/astral-sh/uv:0.4.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install development headers for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3-dev build-essential \
        libdbus-1-dev libdbus-glib-1-dev pkg-config \
        libgirepository1.0-dev libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv && \
    uv pip install -r requirements.txt && \
    uv pip install hyperdx-opentelemetry

# frontend app
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /app/frontendts
COPY frontendts/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --legacy-peer-deps
ARG VITE_WEBSITE_DOMAIN
COPY frontendts/ ./
ENV VITE_WEBSITE_DOMAIN=$VITE_WEBSITE_DOMAIN \
    NODE_OPTIONS=--max-old-space-size=4096
RUN npm run build

# LAStools
FROM base AS lastools-builder
WORKDIR /tmp/las
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates && \
    rm -rf /var/lib/apt/lists/*
RUN wget https://downloads.rapidlasso.de/LAStools.tar.gz && \
    tar -xzf LAStools.tar.gz && \
    cp bin/las2las64 /usr/local/bin/ && \
    chmod +x /usr/local/bin/las2las64 && \
    cp bin/lasinfo64 /usr/local/bin/lasinfo64 && \
    chmod +x /usr/local/bin/lasinfo64 && \
    rm -rf /tmp/las

# final stage
FROM tools AS final
WORKDIR /app

# Install legacy libraries for MapLibre compatibility
RUN dpkgArch="$(dpkg --print-architecture)" && \
    wget -qO /tmp/multiarch.deb \
      http://snapshot.debian.org/archive/debian/20190501T215844Z/pool/main/g/glibc/multiarch-support_2.28-10_${dpkgArch}.deb && \
    wget -qO /tmp/libjpeg8.deb \
      http://snapshot.debian.org/archive/debian/20141009T042436Z/pool/main/libj/libjpeg8/libjpeg8_8d1-2_${dpkgArch}.deb && \
    wget -qO /tmp/libicu70.deb \
      http://archive.ubuntu.com/ubuntu/pool/main/i/icu/libicu70_70.1-2ubuntu1_${dpkgArch}.deb && \
    wget -qO /tmp/libpng.deb \
      http://ftp.debian.org/debian/pool/main/libp/libpng1.6/libpng16-16_1.6.37-3_${dpkgArch}.deb && \
    apt-get purge -y libpng-dev && \
    apt-get update && \
    apt-get install -y /tmp/multiarch.deb /tmp/libjpeg8.deb /tmp/libicu70.deb && \
    dpkg -i /tmp/libpng.deb && \
    rm /tmp/*.deb && rm -rf /var/lib/apt/lists/*

# Install MapLibre and Node dependencies
COPY --from=maplibre-builder /opt/maplibre-native/platform/node/*.tgz /tmp/
RUN --mount=type=cache,target=/root/.npm \
    npm install --production --ignore-scripts /tmp/*.tgz \
    && npm install --production sharp @mapbox/geo-viewport \
    && rm -rf /tmp/*.tgz

# Copy Python virtual environment from builder
COPY --from=python-builder /app/.venv /app/.venv
COPY --from=ghcr.io/astral-sh/uv:0.4.9 /uv /bin/uv
ENV PATH="/app/.venv/bin:$PATH"

COPY --from=lastools-builder /usr/local/bin/las2las64 /usr/local/bin/las2las64
COPY --from=lastools-builder /usr/local/bin/lasinfo64 /usr/local/bin/lasinfo64

# Copy application files
COPY . /app/
COPY --from=frontend-builder /app/frontendts/dist /app/frontendts/dist

# Setup environment
ENV DISPLAY=:99 \
    LANG=en_US.UTF-8 \
    PYTHONPATH="/app:/usr/local/lib/python3.11/dist-packages:/usr/lib/python3/dist-packages" \
    LD_LIBRARY_PATH="/usr/local/lib:/usr/lib" \
    GDAL_DATA="/usr/local/share/gdal" \
    GDAL_DRIVER_PATH="/usr/local/lib/gdalplugins"

CMD ["python", "-m", "src.wsgi"]
