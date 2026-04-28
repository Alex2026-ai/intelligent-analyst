/**
 * AUTH CONTEXT (Days 14-16)
 *
 * Centralized authentication and RBAC state management.
 * SECURITY: UI reflects server-enforced permissions - never relies on hiding as security.
 *
 * Roles:
 * - user: Standard access, can view own batches
 * - auditor: Read-only access across tenant
 * - tenant_admin: Can place legal holds, manage tenant data
 * - platform_admin: Full access, can switch tenants, release holds
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { auth, firebaseConfigReady } from '../firebase';
import { onAuthStateChanged } from 'firebase/auth';
import { setActiveRegion, getDefaultRegion } from '../api/region';

// ============================================================================
// RBAC PERMISSIONS
// ============================================================================

const ROLE_HIERARCHY = {
  user: 0,
  auditor: 1,
  tenant_admin: 2,
  platform_admin: 3,
};

const PERMISSIONS = {
  // Batch Operations
  VIEW_BATCHES: ['user', 'auditor', 'tenant_admin', 'platform_admin'],
  UPLOAD_BATCH: ['user', 'tenant_admin', 'platform_admin'],
  ABORT_BATCH: ['user', 'tenant_admin', 'platform_admin'],

  // Audit Operations
  VIEW_AUDIT: ['user', 'auditor', 'tenant_admin', 'platform_admin'],
  EXPORT_AUDIT: ['user', 'auditor', 'tenant_admin', 'platform_admin'],

  // Legal Hold Operations (Governance)
  VIEW_HOLD_STATUS: ['auditor', 'tenant_admin', 'platform_admin'],
  PLACE_HOLD: ['tenant_admin', 'platform_admin'],
  RELEASE_HOLD: ['platform_admin'],
  VIEW_HOLD_HISTORY: ['auditor', 'tenant_admin', 'platform_admin'],

  // Tenant Operations
  SWITCH_TENANT: ['platform_admin'],
  VIEW_ALL_TENANTS: ['platform_admin'],

  // Admin Operations
  VIEW_SECURITY_STATUS: ['tenant_admin', 'platform_admin'],
  VIEW_RETENTION_STATUS: ['tenant_admin', 'platform_admin'],
  APPLY_LIFECYCLE_POLICY: ['platform_admin'],
  SIMULATE_PURGE: ['platform_admin'],
};

// ============================================================================
// AUTH CONTEXT
// ============================================================================

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  // User state
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Token/claims state
  const [idToken, setIdToken] = useState(null);
  const [claims, setClaims] = useState(null);

  // Tenant state (for platform admins)
  const [activeTenantId, setActiveTenantId] = useState(null);
  const [availableTenants, setAvailableTenants] = useState([]);

  // Region state
  const [tenantRegion, setTenantRegion] = useState(getDefaultRegion());

  // Derive role from claims
  const role = claims?.role || 'user';
  const tenantId = claims?.tenant_id || activeTenantId || null;

  // ============================================================================
  // PERMISSION HELPERS
  // ============================================================================

  /**
   * Check if current user can perform a specific action.
   * This is the CORE RBAC function - use this everywhere.
   */
  const canPerform = useCallback((action) => {
    if (!role) return false;

    const allowedRoles = PERMISSIONS[action];
    if (!allowedRoles) {
      console.warn(`Unknown permission: ${action}`);
      return false;
    }

    return allowedRoles.includes(role);
  }, [role]);

  /**
   * Check if current role has at least the specified role level.
   */
  const hasRoleLevel = useCallback((requiredRole) => {
    const currentLevel = ROLE_HIERARCHY[role] || 0;
    const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;
    return currentLevel >= requiredLevel;
  }, [role]);

  /**
   * Check if user is a platform admin.
   */
  const isPlatformAdmin = useCallback(() => {
    return role === 'platform_admin';
  }, [role]);

  /**
   * Check if user is at least a tenant admin.
   */
  const isTenantAdmin = useCallback(() => {
    return role === 'tenant_admin' || role === 'platform_admin';
  }, [role]);

  // ============================================================================
  // TENANT MANAGEMENT (Platform Admin Only)
  // ============================================================================

  /**
   * Switch active tenant context.
   * SECURITY: Only platform_admin can switch tenants.
   * Clears local state to prevent data bleed between tenants.
   */
  const switchTenant = useCallback((newTenantId) => {
    if (!canPerform('SWITCH_TENANT')) {
      console.error('Unauthorized: Cannot switch tenant without platform_admin role');
      return false;
    }

    console.log(`[AuthContext] Switching tenant: ${activeTenantId} -> ${newTenantId}`);
    setActiveTenantId(newTenantId);

    // Emit event for other components to clear their state
    window.dispatchEvent(new CustomEvent('tenantSwitched', {
      detail: { previousTenant: activeTenantId, newTenant: newTenantId }
    }));

    // Reset region to default — backend 403 will catch actual mismatches
    setTenantRegion(getDefaultRegion());
    setActiveRegion(getDefaultRegion());

    return true;
  }, [activeTenantId, canPerform]);

  /**
   * Get the effective tenant ID for API requests.
   * For tenant_admin: Always their own tenant (immutable)
   * For platform_admin: The active tenant from switcher
   */
  const getEffectiveTenantId = useCallback(() => {
    if (isPlatformAdmin() && activeTenantId) {
      return activeTenantId;
    }
    return tenantId;
  }, [isPlatformAdmin, activeTenantId, tenantId]);

  // ============================================================================
  // AUTH STATE MANAGEMENT
  // ============================================================================

  useEffect(() => {
    if (!firebaseConfigReady || !auth) {
      setError('Dashboard sign-in is not configured for this deployment.');
      setLoading(false);
      return undefined;
    }

    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      try {
        if (firebaseUser) {
          // Get ID token and claims
          const token = await firebaseUser.getIdToken();
          const tokenResult = await firebaseUser.getIdTokenResult();

          setUser(firebaseUser);
          setIdToken(token);
          setClaims(tokenResult.claims);

          // Set initial tenant from claims
          if (tokenResult.claims.tenant_id) {
            setActiveTenantId(tokenResult.claims.tenant_id);
          }

          // Set region from claims or default
          const region = tokenResult.claims.tenant_region || getDefaultRegion();
          setTenantRegion(region);
          setActiveRegion(region);

          console.log('[AuthContext] User authenticated:', {
            uid: firebaseUser.uid,
            email: firebaseUser.email,
            role: tokenResult.claims.role || 'user',
            tenantId: tokenResult.claims.tenant_id,
            region,
          });
        } else {
          setUser(null);
          setIdToken(null);
          setClaims(null);
          setActiveTenantId(null);
          setTenantRegion(getDefaultRegion());
          setActiveRegion(getDefaultRegion());
        }
      } catch (err) {
        console.error('[AuthContext] Auth error:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    });

    return () => unsubscribe();
  }, []);

  // Refresh token periodically
  useEffect(() => {
    if (!user) return;

    const refreshToken = async () => {
      try {
        const token = await user.getIdToken(true);
        setIdToken(token);
      } catch (err) {
        console.error('[AuthContext] Token refresh failed:', err);
      }
    };

    // Refresh every 50 minutes (tokens expire at 60)
    const interval = setInterval(refreshToken, 50 * 60 * 1000);
    return () => clearInterval(interval);
  }, [user]);

  // ============================================================================
  // CONTEXT VALUE
  // ============================================================================

  const value = {
    // User state
    user,
    loading,
    error,
    idToken,
    claims,

    // Role/permission helpers
    role,
    canPerform,
    hasRoleLevel,
    isPlatformAdmin,
    isTenantAdmin,

    // Tenant management
    tenantId,
    activeTenantId,
    availableTenants,
    setAvailableTenants,
    switchTenant,
    getEffectiveTenantId,
    tenantRegion,

    // Convenience flags
    isAuthenticated: !!user,
    canPlaceHold: canPerform('PLACE_HOLD'),
    canReleaseHold: canPerform('RELEASE_HOLD'),
    canSwitchTenant: canPerform('SWITCH_TENANT'),
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
