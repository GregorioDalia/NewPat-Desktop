# Scientific base and CRAN snapshot are pinned inputs. Changes require the
# scientific regression suite against the resulting image.
FROM rocker/r-ver:4.4.2@sha256:df26749182af64d5263bf64149d51a427b476ed28c4e046997143be3f97fdd7c

ARG SAMTOOLS_VERSION=1.21
ARG SAMTOOLS_SHA256=05724b083a6b6f0305fcae5243a056cc36cf826309c3cb9347a6b89ee3fc5ada
ENV NEWPAT_CRAN_REPOSITORY=https://p3m.dev/cran/__linux__/noble/2025-02-27

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libbz2-dev \
        libcairo2-dev \
        libcurl4-openssl-dev \
        libfontconfig1-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libicu-dev \
        libjpeg-dev \
        liblzma-dev \
        libncurses-dev \
        libpng-dev \
        libssl-dev \
        libtiff-dev \
        libxml2-dev \
        python3 \
        zlib1g-dev \
    && curl -fsSL \
        "https://github.com/samtools/samtools/releases/download/${SAMTOOLS_VERSION}/samtools-${SAMTOOLS_VERSION}.tar.bz2" \
        -o /tmp/samtools.tar.bz2 \
    && printf '%s  %s\n' "$SAMTOOLS_SHA256" /tmp/samtools.tar.bz2 | sha256sum --check --strict - \
    && mkdir -p /tmp/samtools-src \
    && tar -xjf /tmp/samtools.tar.bz2 -C /tmp/samtools-src --strip-components=1 \
    && cd /tmp/samtools-src \
    && ./configure --prefix=/usr/local \
    && make -j"$(nproc)" \
    && make install \
    && install -D -m 0644 LICENSE /usr/share/doc/newpat-samtools/samtools/LICENSE \
    && install -D -m 0644 "htslib-${SAMTOOLS_VERSION}/LICENSE" \
        /usr/share/doc/newpat-samtools/htslib/LICENSE \
    && install -D -m 0644 "htslib-${SAMTOOLS_VERSION}/htscodecs/LICENSE.md" \
        /usr/share/doc/newpat-samtools/htscodecs/LICENSE.md \
    && install -D -m 0644 lz4/LICENSE /usr/share/doc/newpat-samtools/lz4/LICENSE \
    && rm -rf /tmp/samtools-src /tmp/samtools.tar.bz2 \
    && install -d /usr/share/newpat \
    && dpkg-query -W -f='${Package}\t${Version}\n' > /usr/share/newpat/apt-versions.tsv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN install2.r --error --skipinstalled --ncpus -1 --repos "$NEWPAT_CRAN_REPOSITORY" \
      argparse \
      ComplexUpset \
      jsonlite \
      openxlsx \
      optparse \
      patchwork \
      readxl \
      tidyverse

COPY docker/scientific-runtime/r-packages.tsv /usr/share/newpat/r-packages.tsv
COPY docker/scientific-runtime/verify-packages.R /usr/local/lib/newpat/verify-packages.R
RUN Rscript /usr/local/lib/newpat/verify-packages.R \
    && samtools --version | head -n 1 \
    && R --version | head -n 1

# Cairo embeds readable Latin/Greek sample labels in presentation PDF copies.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && dpkg-query -W -f='${Package}\t${Version}\n' > /usr/share/newpat/apt-versions.tsv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Bundle only reviewed code and notices. Do not copy arbitrary local files or
# mount the host project over this path in production.
COPY LICENSE THIRD_PARTY_NOTICES.md /opt/newpat/
COPY scientific/SHA256SUMS /opt/newpat/scientific/SHA256SUMS
COPY scientific/vendor/DNPcall/DNPcall.R scientific/vendor/DNPcall/LICENSE /opt/newpat/scientific/vendor/DNPcall/
COPY scientific/vendor/NEWPAT/LICENSE /opt/newpat/scientific/vendor/NEWPAT/LICENSE
COPY scientific/vendor/NEWPAT/SNPcall/SNPcall.R /opt/newpat/scientific/vendor/NEWPAT/SNPcall/SNPcall.R
COPY scientific/vendor/NEWPAT/contamination/detect_contamination.R /opt/newpat/scientific/vendor/NEWPAT/contamination/detect_contamination.R
COPY scientific/vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R /opt/newpat/scientific/vendor/NEWPAT/CPI_from_cffDNA/cfDNA_CPI_estimator.R
COPY scientific/vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R /opt/newpat/scientific/vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R
COPY scientific/vendor/NEWPAT/Fetal_sex/Fetal_sex.R /opt/newpat/scientific/vendor/NEWPAT/Fetal_sex/Fetal_sex.R
COPY src/newpat_scientific/fetal_sex.py src/newpat_scientific/cpin.py src/newpat_scientific/settings.py src/newpat_scientific/settings.R src/newpat_scientific/settings_data.json /opt/newpat/lib/newpat_scientific/
COPY engine/main.py /opt/newpat/engine/main.py
COPY src/newpat_scientific/__init__.py src/newpat_scientific/errors.py src/newpat_scientific/panels.py src/newpat_scientific/files.py src/newpat_scientific/contamination.py src/newpat_scientific/snp.py src/newpat_scientific/snp_summary.py src/newpat_scientific/snp_parallel.py src/newpat_scientific/dnp.py src/newpat_scientific/cpi.py src/newpat_scientific/catalog.py src/newpat_scientific/plan.py src/newpat_scientific/executor.py src/newpat_scientific/desktop_scheduling.py src/newpat_scientific/outputs.py src/newpat_scientific/presentation.py src/newpat_scientific/presentation.R src/newpat_scientific/plots.R src/newpat_scientific/performance.py /opt/newpat/lib/newpat_scientific/
COPY src/newpat_scientific/catalog_data/ /opt/newpat/lib/newpat_scientific/catalog_data/
COPY src/newpat_scientific/scratch.py src/newpat_scientific/dnp_pileup.py src/newpat_scientific/dnp_blocks.R src/newpat_scientific/progress.py src/newpat_scientific/progress.R /opt/newpat/lib/newpat_scientific/
COPY src/newpat_scientific/parallel.py src/newpat_scientific/parallel.R /opt/newpat/lib/newpat_scientific/
RUN python3 /opt/newpat/engine/main.py verify \
    && python3 /opt/newpat/engine/main.py catalog --json > /tmp/newpat-catalog-check.json \
    && rm /tmp/newpat-catalog-check.json

# Docker copies this directory metadata into each new anonymous volume.
# Mode 1777 permits the selected non-root Linux user to create private scratch.
RUN install -d -m 1777 /scratch

# The client explicitly selects the bundled workflow or an isolated runtime probe.
WORKDIR /workspace/newpat-desktop
