# Stage 1: Build the Rust binary
FROM rust:latest AS builder

# Install dependencies for cross-compilation
RUN apt update && apt install -y \
    gcc-x86-64-linux-gnu \
    libc6-dev-amd64-cross && \
    rm -rf /var/lib/apt/lists/*

# Add the Linux target for Rust
RUN rustup target add x86_64-unknown-linux-gnu

# Set the working directory
WORKDIR /app
ENV AWS_REGION=us-east-1

# Copy the source code
COPY . .

# Build the project for the Linux target
RUN cargo build --release --target x86_64-unknown-linux-gnu

# Stage 2: Extract the built binary
FROM debian:latest AS runtime

# Copy the compiled binary from the builder stage
COPY --from=builder /app/target/x86_64-unknown-linux-gnu/release/eu4_parser /eu4_parser

# Set the entry point
ENTRYPOINT ["/eu4_parser"]
