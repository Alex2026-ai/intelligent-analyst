import "./index.css";
import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import ErrorBoundary from "./ErrorBoundary";
import RouteMetadata from "./marketing/components/RouteMetadata";

const AuthenticatedDashboardRoute = lazy(() => import("./routes/AuthenticatedDashboardRoute"));
const SharedBatchView = lazy(() => import("./SharedBatchView"));
const DashboardPreview = lazy(() => import("./DashboardPreview"));

const Homepage = lazy(() => import("./marketing/pages/Homepage"));
const Product = lazy(() => import("./marketing/pages/Product"));
const PlatformPage = lazy(() => import("./marketing/pages/Platform"));
const ForensicAudit = lazy(() => import("./marketing/pages/ForensicAudit"));
const TrustArchitecture = lazy(() => import("./marketing/pages/TrustArchitecture"));
const UseCases = lazy(() => import("./marketing/pages/UseCases"));
const RequestDemo = lazy(() => import("./marketing/pages/RequestDemo"));
const NotFound = lazy(() => import("./marketing/pages/NotFound"));
const Capture = lazy(() => import("./marketing/pages/Capture"));

const Protocol = lazy(() => import("./marketing/pages/Protocol"));
const Verify = lazy(() => import("./marketing/pages/Verify"));
const Compliance = lazy(() => import("./marketing/pages/Compliance"));
const TrustFeedPage = lazy(() => import("./marketing/pages/TrustFeed"));
const IAVPv1 = lazy(() => import("./marketing/pages/protocol/IAVPv1"));
const EvidencePackSample = lazy(() => import("./marketing/pages/samples/EvidencePackSample"));
const ResourcesHub = lazy(() => import("./marketing/pages/ResourcesHub"));
const Glossary = lazy(() => import("./marketing/pages/Glossary"));
const LegalPage = lazy(() => import("./marketing/pages/LegalPage"));
const Company = lazy(() => import("./marketing/pages/Company"));
const TransparencyManifesto = lazy(() => import("./marketing/pages/TransparencyManifesto"));

const root = document.getElementById("root");

if (!root) {
  throw new Error("Root element #root not found");
}

function RouteFallback() {
  return (
    <div className="min-h-screen bg-[#050b14] flex items-center justify-center" aria-label="Loading">
      <div className="h-8 w-8 rounded-full border-2 border-cyan-400/30 border-t-cyan-400 animate-spin" />
    </div>
  );
}

function SharedBatchWrapper() {
  const path = window.location.pathname;
  const shareMatch = path.match(/^\/s\/([^/]+)\/?$/);
  const shareToken = shareMatch ? shareMatch[1] : "";
  return <SharedBatchView shareToken={shareToken} />;
}

function App() {
  return (
    <BrowserRouter>
      <RouteMetadata />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* Marketing pages */}
          <Route path="/" element={<Homepage />} />
          <Route path="/product" element={<Product />} />
          <Route path="/platform" element={<PlatformPage />} />
          <Route path="/security" element={<ForensicAudit />} />
          <Route path="/forensic-audit" element={<ForensicAudit />} />
          <Route path="/trust-architecture" element={<TrustArchitecture />} />
          <Route path="/request-demo" element={<RequestDemo />} />

          {/* Use cases — index + detail */}
          <Route path="/use-cases" element={<UseCases />} />
          <Route path="/use-cases/:slug" element={<UseCases />} />

          {/* Capture routes for marketing asset generation */}
          <Route path="/__capture/:type" element={<Capture />} />

          {/* Trust Center */}
          <Route path="/protocol" element={<Protocol />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/compliance" element={<Compliance />} />
          <Route path="/trust-feed" element={<TrustFeedPage />} />

          {/* Protocol specifications (full formal spec) */}
          <Route path="/protocol/iavp/v1" element={<IAVPv1 />} />

          {/* Sample artifacts */}
          <Route path="/samples/evidence-pack" element={<EvidencePackSample />} />

          {/* Resources hub (quiet launch - no nav promotion) */}
          <Route path="/resources" element={<ResourcesHub />} />

          {/* Glossary (SEO authority anchor - no nav promotion) */}
          <Route path="/glossary" element={<Glossary />} />

          {/* Transparency manifesto */}
          <Route path="/transparency-manifesto" element={<TransparencyManifesto />} />

          {/* Company */}
          <Route path="/company" element={<Company />} />

          {/* Legal pages */}
          <Route path="/privacy" element={<LegalPage type="privacy" />} />
          <Route path="/terms" element={<LegalPage type="terms" />} />
          <Route path="/dpa" element={<LegalPage type="dpa" />} />

          {/* Application routes */}
          <Route path="/app" element={<AuthenticatedDashboardRoute />} />
          <Route path="/app/*" element={<AuthenticatedDashboardRoute />} />
          <Route path="/preview" element={<DashboardPreview />} />
          <Route path="/s/:shareToken" element={<SharedBatchWrapper />} />

          {/* 404 catch-all — must be last */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);
