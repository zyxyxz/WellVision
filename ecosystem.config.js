module.exports = {
  apps: [
    {
      name: "wellvision-api",
      cwd: "./backend",
      script: "uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8010",
      interpreter: "python3",
      env: {
        ENV: process.env.ENV,
        SECRET_KEY: process.env.SECRET_KEY,
        DATABASE_URL: process.env.DATABASE_URL,
        REDIS_URL: process.env.REDIS_URL,
        OBJECT_STORE_PROVIDER: process.env.OBJECT_STORE_PROVIDER,
        OBJECT_STORE_BUCKET: process.env.OBJECT_STORE_BUCKET,
        OBJECT_STORE_REGION: process.env.OBJECT_STORE_REGION,
        S3_ENDPOINT_URL: process.env.S3_ENDPOINT_URL,
        AWS_ACCESS_KEY_ID: process.env.AWS_ACCESS_KEY_ID,
        AWS_SECRET_ACCESS_KEY: process.env.AWS_SECRET_ACCESS_KEY,
        TOS_ENDPOINT: process.env.TOS_ENDPOINT,
        TOS_REGION: process.env.TOS_REGION,
        TOS_ACCESS_KEY: process.env.TOS_ACCESS_KEY,
        TOS_SECRET_KEY: process.env.TOS_SECRET_KEY,
        TOS_BUCKET: process.env.TOS_BUCKET,
        CORS_ALLOW_ORIGINS: process.env.CORS_ALLOW_ORIGINS,
        BOOTSTRAP_TENANT_NAME: process.env.BOOTSTRAP_TENANT_NAME,
        BOOTSTRAP_ADMIN_EMAIL: process.env.BOOTSTRAP_ADMIN_EMAIL,
        BOOTSTRAP_ADMIN_PASSWORD: process.env.BOOTSTRAP_ADMIN_PASSWORD,
        HTTP_PROXY: "",
        HTTPS_PROXY: "",
        ALL_PROXY: "",
        http_proxy: "",
        https_proxy: "",
        all_proxy: "",
        NO_PROXY: "localhost,127.0.0.1,::1,*.aisp24.com,wellvision.aisp24.com"
      }
    },
    {
      name: "wellvision-frontend",
      cwd: "./frontend",
      script: "npm",
      args: "run dev -- --host 0.0.0.0 --port 5173",
      interpreter: "none",
      env: {
        NODE_ENV: "development",
        VITE_API_BASE_URL: process.env.VITE_API_BASE_URL || "/api"
      }
    }
  ]
};
