#!/bin/bash

# Discord Voice-to-Text Bot Deployment Script
# Author: Discord Voice-to-Text Bot Team
# Description: Automated deployment script for Linux servers

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}" >&2
}

warning() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

info() {
    echo -e "${BLUE}[INFO] $1${NC}"
}

# Configuration
PROJECT_NAME="discord-voice-to-text"
COMPOSE_PROJECT_NAME="discord-voice-to-text"
BACKUP_DIR="/opt/backups/${PROJECT_NAME}"
DATA_DIR="./data"

# Function to check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
        error "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
        error "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    # Check if .env file exists
    if [[ ! -f .env ]]; then
        error ".env file not found. Please create one from .env.example"
        error "Run: cp .env.example .env && nano .env"
        exit 1
    fi
    
    # Check if required environment variables are set
    source .env
    if [[ -z "$DISCORD_TOKEN" ]]; then
        error "DISCORD_TOKEN is not set in .env file"
        exit 1
    fi
    
    if [[ -z "$OPENAI_API_KEY" ]]; then
        error "OPENAI_API_KEY is not set in .env file"
        exit 1
    fi
    
    log "Prerequisites check passed ✓"
}

# Function to create necessary directories
create_directories() {
    log "Creating necessary directories..."
    
    mkdir -p ${DATA_DIR}/recordings
    mkdir -p ${DATA_DIR}/logs
    mkdir -p ${BACKUP_DIR}
    
    # Set appropriate permissions
    chmod 755 ${DATA_DIR}
    chmod 755 ${DATA_DIR}/recordings
    chmod 755 ${DATA_DIR}/logs
    
    log "Directories created ✓"
}

# Function to backup existing data
backup_data() {
    if [[ -d "${DATA_DIR}" && "$(ls -A ${DATA_DIR})" ]]; then
        log "Backing up existing data..."
        
        BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        BACKUP_PATH="${BACKUP_DIR}/backup_${BACKUP_TIMESTAMP}"
        
        cp -r ${DATA_DIR} ${BACKUP_PATH}
        log "Data backed up to ${BACKUP_PATH} ✓"
    fi
}

# Function to pull latest images
pull_images() {
    log "Pulling latest Docker images..."
    docker-compose pull
    log "Images pulled ✓"
}

# Function to build the application
build_app() {
    log "Building application..."
    docker-compose build --no-cache
    log "Application built ✓"
}

# Function to stop existing containers
stop_containers() {
    log "Stopping existing containers..."
    docker-compose down
    log "Containers stopped ✓"
}

# Function to start containers
start_containers() {
    log "Starting containers..."
    docker-compose up -d
    log "Containers started ✓"
}

# Function to check health
check_health() {
    log "Checking application health..."
    
    # Wait for container to start
    sleep 10
    
    # Check if container is running
    if docker-compose ps | grep -q "Up"; then
        log "Application is running ✓"
        
        # Show logs for verification
        info "Recent logs:"
        docker-compose logs --tail=20
        
        return 0
    else
        error "Application failed to start"
        error "Logs:"
        docker-compose logs --tail=50
        return 1
    fi
}

# Function to show status
show_status() {
    log "Application Status:"
    docker-compose ps
    
    echo
    info "To view logs: docker-compose logs -f"
    info "To stop: docker-compose down"
    info "To restart: docker-compose restart"
}

# Function to cleanup old images
cleanup() {
    log "Cleaning up old Docker images..."
    docker system prune -f
    log "Cleanup completed ✓"
}

# Main deployment function
deploy() {
    log "Starting deployment of ${PROJECT_NAME}..."
    
    check_prerequisites
    create_directories
    backup_data
    stop_containers
    pull_images
    build_app
    start_containers
    
    if check_health; then
        log "Deployment completed successfully! 🎉"
        show_status
        cleanup
    else
        error "Deployment failed"
        exit 1
    fi
}

# Function to show usage
usage() {
    echo "Usage: $0 [COMMAND]"
    echo
    echo "Commands:"
    echo "  deploy      Full deployment (default)"
    echo "  start       Start containers"
    echo "  stop        Stop containers"
    echo "  restart     Restart containers"
    echo "  logs        Show logs"
    echo "  status      Show status"
    echo "  backup      Backup data"
    echo "  cleanup     Cleanup old images"
    echo "  update      Update and restart"
    echo "  help        Show this help"
    echo
}

# Command line argument processing
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    start)
        log "Starting containers..."
        docker-compose up -d
        show_status
        ;;
    stop)
        log "Stopping containers..."
        docker-compose down
        ;;
    restart)
        log "Restarting containers..."
        docker-compose restart
        show_status
        ;;
    logs)
        docker-compose logs -f
        ;;
    status)
        show_status
        ;;
    backup)
        backup_data
        ;;
    cleanup)
        cleanup
        ;;
    update)
        log "Updating application..."
        check_prerequisites
        backup_data
        stop_containers
        pull_images
        build_app
        start_containers
        check_health
        show_status
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        error "Unknown command: $1"
        usage
        exit 1
        ;;
esac