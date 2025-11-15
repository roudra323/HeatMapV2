#!/usr/bin/env node

/**
 * Script to copy visualization_data.json from backend to frontend public folder
 * Usage: node scripts/copy-data.js
 */

const fs = require('fs');
const path = require('path');

const backendDataPath = path.join(__dirname, '../../backend/data/results/visualization_data.json');
const frontendDataDir = path.join(__dirname, '../public/data');
const frontendDataPath = path.join(frontendDataDir, 'visualization_data.json');

try {
  // Check if backend data exists
  if (!fs.existsSync(backendDataPath)) {
    console.error(`❌ Error: Backend data file not found at ${backendDataPath}`);
    console.error('   Please run "python visualize.py" in the backend directory first.');
    process.exit(1);
  }

  // Create data directory if it doesn't exist
  if (!fs.existsSync(frontendDataDir)) {
    fs.mkdirSync(frontendDataDir, { recursive: true });
    console.log(`✅ Created directory: ${frontendDataDir}`);
  }

  // Copy the file
  fs.copyFileSync(backendDataPath, frontendDataPath);
  
  const stats = fs.statSync(frontendDataPath);
  const fileSizeMB = (stats.size / (1024 * 1024)).toFixed(2);
  
  console.log(`✅ Successfully copied visualization data`);
  console.log(`   From: ${backendDataPath}`);
  console.log(`   To:   ${frontendDataPath}`);
  console.log(`   Size: ${fileSizeMB} MB`);
  console.log(`\n📝 Next steps:`);
  console.log(`   1. Set NEXT_PUBLIC_DATA_SOURCE=local in your .env.local file`);
  console.log(`   2. Restart your Next.js dev server`);
} catch (error) {
  console.error('❌ Error copying data:', error.message);
  process.exit(1);
}

