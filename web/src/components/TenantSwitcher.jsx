/**
 * TENANT SWITCHER (Days 14-16)
 *
 * Global tenant context switcher for Platform Admins.
 * Allows viewing and managing data across infrastructure partners.
 *
 * SECURITY:
 * - Only visible/functional for platform_admin role
 * - Switching tenant flushes local cache to prevent data bleed
 * - Server still enforces authorization on all requests
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Building2, ChevronDown, Check, Search, Loader2,
  Users, ShieldCheck, AlertTriangle
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { fetchAdminTenants } from '../api/client';

// ============================================================================
// TENANT SWITCHER COMPONENT
// ============================================================================

const TenantSwitcher = ({ onTenantChange, className = '' }) => {
  const { canPerform, activeTenantId, switchTenant, setAvailableTenants } = useAuth();

  // State
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Refs
  const dropdownRef = useRef(null);
  const searchRef = useRef(null);

  // Check permission
  const canSwitch = canPerform('SWITCH_TENANT');

  // Find current tenant
  const currentTenant = tenants.find(t => t.id === activeTenantId) || {
    id: activeTenantId,
    name: activeTenantId || 'All Tenants',
    batchCount: null,
  };

  // Filter tenants by search
  const filteredTenants = tenants.filter(t =>
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.id.toLowerCase().includes(search.toLowerCase())
  );

  // ============================================================================
  // EFFECTS
  // ============================================================================

  // Fetch tenants on mount (if authorized)
  useEffect(() => {
    if (!canSwitch) return;

    const loadTenants = async () => {
      setLoading(true);
      setError(null);

      try {
        const result = await fetchAdminTenants();
        if (result.ok && result.data) {
          const tenantList = result.data.tenants || [];
          setTenants(tenantList);
          setAvailableTenants(tenantList);
        } else {
          setError(result.error || 'Failed to load tenants');
        }
      } catch (err) {
        setError(err.message || 'Failed to load tenants');
      } finally {
        setLoading(false);
      }
    };

    loadTenants();
  }, [canSwitch, setAvailableTenants]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
        setSearch('');
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchRef.current) {
      setTimeout(() => searchRef.current?.focus(), 100);
    }
  }, [isOpen]);

  // ============================================================================
  // HANDLERS
  // ============================================================================

  const handleTenantSelect = (tenant) => {
    if (tenant.id === activeTenantId) {
      setIsOpen(false);
      return;
    }

    // Switch tenant (this will emit tenantSwitched event)
    const success = switchTenant(tenant.id);

    if (success) {
      setIsOpen(false);
      setSearch('');

      // Notify parent
      if (onTenantChange) {
        onTenantChange(tenant.id, tenant);
      }
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  // Don't render if not authorized
  if (!canSwitch) {
    return null;
  }

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all ${
          isOpen
            ? 'bg-violet-500/10 border-violet-500/40 text-violet-400'
            : 'bg-slate-800/50 border-slate-700 text-slate-300 hover:border-slate-600 hover:text-white'
        }`}
      >
        <Building2 className="w-4 h-4" />
        <div className="text-left">
          <div className="text-xs text-slate-500 leading-none">Tenant</div>
          <div className="text-sm font-medium truncate max-w-[140px]">
            {currentTenant.name}
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-72 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl overflow-hidden z-50">
          {/* Header */}
          <div className="px-4 py-3 border-b border-slate-800 bg-slate-800/50">
            <div className="flex items-center gap-2 text-violet-400">
              <ShieldCheck className="w-4 h-4" />
              <span className="text-sm font-medium">Platform Admin</span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Switch tenant context to view their data
            </p>
          </div>

          {/* Search */}
          <div className="p-2 border-b border-slate-800">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tenants..."
                className="w-full pl-9 pr-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500/50"
              />
            </div>
          </div>

          {/* Tenant List */}
          <div className="max-h-64 overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 text-violet-400 animate-spin" />
              </div>
            )}

            {error && (
              <div className="flex items-center gap-2 p-4 text-red-400">
                <AlertTriangle className="w-4 h-4" />
                <span className="text-sm">{error}</span>
              </div>
            )}

            {!loading && !error && filteredTenants.length === 0 && (
              <div className="py-8 text-center text-slate-500 text-sm">
                {search ? 'No tenants match your search' : 'No tenants available'}
              </div>
            )}

            {!loading && !error && filteredTenants.map((tenant) => (
              <button
                key={tenant.id}
                onClick={() => handleTenantSelect(tenant)}
                className={`w-full flex items-center justify-between px-4 py-3 text-left transition-colors ${
                  tenant.id === activeTenantId
                    ? 'bg-violet-500/10 text-violet-400'
                    : 'hover:bg-slate-800/50 text-slate-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    tenant.id === activeTenantId
                      ? 'bg-violet-500/20'
                      : 'bg-slate-800'
                  }`}>
                    <Building2 className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-medium">{tenant.name}</div>
                    <div className="text-xs text-slate-500 font-mono">
                      {tenant.id}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {tenant.batchCount !== null && (
                    <span className="text-xs text-slate-500">
                      {tenant.batchCount} batches
                    </span>
                  )}
                  {tenant.id === activeTenantId && (
                    <Check className="w-4 h-4 text-violet-400" />
                  )}
                </div>
              </button>
            ))}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-slate-800 bg-slate-800/30">
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Users className="w-3 h-3" />
              <span>{tenants.length} tenant{tenants.length !== 1 ? 's' : ''} available</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TenantSwitcher;
