import React, { useState, useEffect, useMemo } from 'react';
import {
  ApplicationManifest,
  IntegrationActivityLogEntry,
} from '../types/integrations';
import {
  fetchApplications,
  triggerAppDiscovery,
  updateAppPermissions,
  fetchIntegrationActivity,
} from '../services/integrationApi';

interface ApplicationManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ApplicationManagerModal: React.FC<ApplicationManagerModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'applications' | 'activity'>('applications');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [applications, setApplications] = useState<ApplicationManifest[]>([]);
  const [activityLogs, setActivityLogs] = useState<IntegrationActivityLogEntry[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isDiscovering, setIsDiscovering] = useState<boolean>(false);
  const [expandedAppId, setExpandedAppId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadData = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [apps, acts] = await Promise.all([
        fetchApplications(),
        fetchIntegrationActivity(30).catch(() => []),
      ]);
      setApplications(apps);
      setActivityLogs(acts);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to connect to integration service.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const handleScanDiscovery = async () => {
    setIsDiscovering(true);
    setErrorMsg(null);
    try {
      const refreshed = await triggerAppDiscovery(true);
      setApplications(refreshed);
    } catch (err: any) {
      setErrorMsg(err.message || 'Discovery scan failed.');
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleToggleAppEnabled = async (app: ApplicationManifest, e: React.MouseEvent) => {
    e.stopPropagation();
    const newEnabled = !app.is_enabled;
    // Optimistic UI update
    setApplications((prev) =>
      prev.map((a) => (a.app_id === app.app_id ? { ...a, is_enabled: newEnabled } : a))
    );
    try {
      await updateAppPermissions({
        app_id: app.app_id,
        is_enabled: newEnabled,
      });
    } catch (err: any) {
      // Revert on failure
      setApplications((prev) =>
        prev.map((a) => (a.app_id === app.app_id ? { ...a, is_enabled: !newEnabled } : a))
      );
      setErrorMsg(`Failed to update ${app.display_name}: ${err.message}`);
    }
  };

  const filteredApps = useMemo(() => {
    return applications.filter((app) => {
      const matchesCategory =
        categoryFilter === 'all' || app.category.toLowerCase() === categoryFilter.toLowerCase();
      const matchesSearch =
        !searchQuery ||
        app.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        app.vendor.toLowerCase().includes(searchQuery.toLowerCase()) ||
        app.app_id.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesCategory && matchesSearch;
    });
  }, [applications, categoryFilter, searchQuery]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.72)',
        backdropFilter: 'blur(8px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1rem',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '920px',
          maxWidth: '96vw',
          maxHeight: '88vh',
          backgroundColor: 'rgba(10, 16, 28, 0.94)',
          border: '1px solid rgba(0, 240, 255, 0.28)',
          boxShadow: '0 0 32px rgba(0, 240, 255, 0.15)',
          borderRadius: '8px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: '#F1F3F5',
          fontFamily: 'var(--hud-font-sans, system-ui, sans-serif)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1rem 1.4rem',
            borderBottom: '1px solid rgba(0, 240, 255, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'linear-gradient(90deg, rgba(0, 240, 255, 0.08) 0%, transparent 100%)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <span
              style={{
                fontSize: '1.15rem',
                fontWeight: 700,
                letterSpacing: '0.08em',
                color: '#00F0FF',
                textTransform: 'uppercase',
              }}
            >
              Integrated Applications
            </span>
            <span
              style={{
                fontSize: '0.75rem',
                backgroundColor: 'rgba(0, 240, 255, 0.15)',
                color: '#00F0FF',
                padding: '0.15rem 0.5rem',
                borderRadius: '12px',
                border: '1px solid rgba(0, 240, 255, 0.3)',
              }}
            >
              Phase 5.2 Framework
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
            <button
              onClick={handleScanDiscovery}
              disabled={isDiscovering}
              style={{
                padding: '0.4rem 0.85rem',
                backgroundColor: isDiscovering ? 'rgba(0, 240, 255, 0.1)' : 'rgba(0, 240, 255, 0.2)',
                border: '1px solid #00F0FF',
                color: '#00F0FF',
                borderRadius: '4px',
                cursor: isDiscovering ? 'wait' : 'pointer',
                fontSize: '0.78rem',
                fontWeight: 600,
                letterSpacing: '0.05em',
                transition: 'all 0.2s',
              }}
            >
              {isDiscovering ? 'SCANNING SYSTEM...' : 'REFRESH DISCOVERY'}
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#8993A3',
                cursor: 'pointer',
                fontSize: '1.25rem',
                lineHeight: 1,
                padding: '0.2rem 0.4rem',
              }}
            >
              ✕
            </button>
          </div>
        </div>

        {/* View Tabs & Search Bar */}
        <div
          style={{
            padding: '0.75rem 1.4rem',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '1rem',
            backgroundColor: 'rgba(5, 10, 20, 0.6)',
          }}
        >
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => setActiveTab('applications')}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: activeTab === 'applications' ? '1px solid #00F0FF' : '1px solid transparent',
                backgroundColor: activeTab === 'applications' ? 'rgba(0, 240, 255, 0.15)' : 'transparent',
                color: activeTab === 'applications' ? '#00F0FF' : '#B0B7C3',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              APPLICATIONS ({applications.length})
            </button>
            <button
              onClick={() => setActiveTab('activity')}
              style={{
                padding: '0.35rem 0.75rem',
                borderRadius: '4px',
                border: activeTab === 'activity' ? '1px solid #00F0FF' : '1px solid transparent',
                backgroundColor: activeTab === 'activity' ? 'rgba(0, 240, 255, 0.15)' : 'transparent',
                color: activeTab === 'activity' ? '#00F0FF' : '#B0B7C3',
                fontSize: '0.8rem',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              ACTIVITY AUDIT ({activityLogs.length})
            </button>
          </div>

          {activeTab === 'applications' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <input
                type="text"
                placeholder="Search applications..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '0.35rem 0.7rem',
                  backgroundColor: 'rgba(0, 0, 0, 0.4)',
                  border: '1px solid rgba(0, 240, 255, 0.25)',
                  borderRadius: '4px',
                  color: '#F1F3F5',
                  fontSize: '0.78rem',
                  width: '200px',
                  outline: 'none',
                }}
              />
            </div>
          )}
        </div>

        {/* Category Filters for Applications */}
        {activeTab === 'applications' && (
          <div
            style={{
              padding: '0.5rem 1.4rem',
              display: 'flex',
              gap: '0.4rem',
              borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
              backgroundColor: 'rgba(10, 16, 28, 0.4)',
              overflowX: 'auto',
            }}
          >
            {[
              { id: 'all', label: 'ALL APPS' },
              { id: 'browser', label: 'BROWSERS (Opera GX, Chrome)' },
              { id: 'office', label: 'MICROSOFT OFFICE (Word, Excel, PowerPoint...)' },
              { id: 'messaging', label: 'MESSAGING (Discord, WhatsApp...)' },
            ].map((cat) => (
              <button
                key={cat.id}
                onClick={() => setCategoryFilter(cat.id)}
                style={{
                  padding: '0.25rem 0.6rem',
                  fontSize: '0.72rem',
                  borderRadius: '12px',
                  border: categoryFilter === cat.id ? '1px solid #00F0FF' : '1px solid rgba(255, 255, 255, 0.1)',
                  backgroundColor: categoryFilter === cat.id ? 'rgba(0, 240, 255, 0.12)' : 'transparent',
                  color: categoryFilter === cat.id ? '#00F0FF' : '#8993A3',
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                }}
              >
                {cat.label}
              </button>
            ))}
          </div>
        )}

        {/* Error notification banner if any */}
        {errorMsg && (
          <div
            style={{
              padding: '0.5rem 1.4rem',
              backgroundColor: 'rgba(239, 68, 68, 0.15)',
              borderBottom: '1px solid rgba(239, 68, 68, 0.4)',
              color: '#fca5a5',
              fontSize: '0.78rem',
            }}
          >
            {errorMsg}
          </div>
        )}

        {/* Main Content Area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 1.4rem' }}>
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: '#8993A3' }}>
              Loading applications catalog...
            </div>
          ) : activeTab === 'applications' ? (
            filteredApps.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem', color: '#8993A3' }}>
                No applications matched your filter.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                {filteredApps.map((app) => {
                  const isExpanded = expandedAppId === app.app_id;
                  return (
                    <div
                      key={app.app_id}
                      style={{
                        backgroundColor: 'rgba(15, 23, 42, 0.7)',
                        border: isExpanded
                          ? '1px solid rgba(0, 240, 255, 0.45)'
                          : '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '6px',
                        padding: '0.9rem',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      {/* Top Bar of Application Card */}
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          cursor: 'pointer',
                        }}
                        onClick={() => setExpandedAppId(isExpanded ? null : app.app_id)}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                          <span
                            style={{
                              fontSize: '0.7rem',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              padding: '0.2rem 0.5rem',
                              borderRadius: '4px',
                              backgroundColor:
                                app.category === 'browser'
                                  ? 'rgba(59, 130, 246, 0.2)'
                                  : app.category === 'office'
                                  ? 'rgba(234, 88, 12, 0.2)'
                                  : 'rgba(147, 51, 234, 0.2)',
                              color:
                                app.category === 'browser'
                                  ? '#60a5fa'
                                  : app.category === 'office'
                                  ? '#fb923c'
                                  : '#c084fc',
                              border: '1px solid rgba(255, 255, 255, 0.1)',
                            }}
                          >
                            {app.category}
                          </span>

                          <div>
                            <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#F1F3F5' }}>
                              {app.display_name}
                              <span style={{ fontSize: '0.75rem', color: '#8993A3', marginLeft: '0.5rem' }}>
                                by {app.vendor}
                              </span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: '#B0B7C3', marginTop: '0.15rem' }}>
                              {app.description}
                            </div>
                          </div>
                        </div>

                        {/* Status Pills and Action Toggle */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          {/* Installed Pill */}
                          <span
                            style={{
                              fontSize: '0.7rem',
                              fontWeight: 600,
                              padding: '0.15rem 0.45rem',
                              borderRadius: '4px',
                              backgroundColor: app.is_installed
                                ? 'rgba(34, 197, 94, 0.15)'
                                : 'rgba(100, 116, 139, 0.2)',
                              color: app.is_installed ? '#4ade80' : '#94a3b8',
                              border: `1px solid ${
                                app.is_installed ? 'rgba(34, 197, 94, 0.3)' : 'rgba(100, 116, 139, 0.2)'
                              }`,
                            }}
                            title={app.installed_path || 'Executable not found in standard paths'}
                          >
                            {app.is_installed ? 'INSTALLED' : 'NOT INSTALLED'}
                          </span>

                          {/* Running Pill */}
                          <span
                            style={{
                              fontSize: '0.7rem',
                              fontWeight: 600,
                              padding: '0.15rem 0.45rem',
                              borderRadius: '4px',
                              backgroundColor: app.is_running
                                ? 'rgba(0, 240, 255, 0.15)'
                                : 'rgba(100, 116, 139, 0.15)',
                              color: app.is_running ? '#00F0FF' : '#94a3b8',
                              border: `1px solid ${
                                app.is_running ? 'rgba(0, 240, 255, 0.35)' : 'rgba(100, 116, 139, 0.2)'
                              }`,
                            }}
                            title={
                              app.is_running
                                ? `Active instances: ${app.running_pids.length} PIDs, ${app.running_window_handles.length} HWNDs`
                                : 'No running process detected'
                            }
                          >
                            {app.is_running ? 'RUNNING' : 'STOPPED'}
                          </span>

                          {/* Health Status */}
                          <span
                            style={{
                              fontSize: '0.7rem',
                              fontWeight: 600,
                              padding: '0.15rem 0.45rem',
                              borderRadius: '4px',
                              backgroundColor:
                                app.health_status === 'healthy'
                                  ? 'rgba(34, 197, 94, 0.15)'
                                  : app.health_status === 'degraded'
                                  ? 'rgba(234, 179, 8, 0.15)'
                                  : 'rgba(100, 116, 139, 0.2)',
                              color:
                                app.health_status === 'healthy'
                                  ? '#4ade80'
                                  : app.health_status === 'degraded'
                                  ? '#facc15'
                                  : '#94a3b8',
                              border: '1px solid rgba(255, 255, 255, 0.1)',
                            }}
                          >
                            {app.health_status.toUpperCase()}
                          </span>

                          {/* Enable/Disable Toggle Switch */}
                          <button
                            onClick={(e) => handleToggleAppEnabled(app, e)}
                            style={{
                              padding: '0.25rem 0.6rem',
                              backgroundColor: app.is_enabled
                                ? 'rgba(0, 240, 255, 0.2)'
                                : 'rgba(239, 68, 68, 0.15)',
                              border: `1px solid ${app.is_enabled ? '#00F0FF' : '#ef4444'}`,
                              color: app.is_enabled ? '#00F0FF' : '#fca5a5',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.72rem',
                              fontWeight: 700,
                            }}
                          >
                            {app.is_enabled ? 'ENABLED' : 'DISABLED'}
                          </button>

                          <span style={{ color: '#8993A3', fontSize: '0.8rem', marginLeft: '0.3rem' }}>
                            {isExpanded ? '▲' : '▼'}
                          </span>
                        </div>
                      </div>

                      {/* Expandable Details (Providers & Capabilities) */}
                      {isExpanded && (
                        <div
                          style={{
                            marginTop: '0.85rem',
                            paddingTop: '0.85rem',
                            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                          }}
                        >
                          {/* Supported Integration Providers */}
                          <div style={{ marginBottom: '0.8rem' }}>
                            <span style={{ fontSize: '0.72rem', color: '#8993A3', fontWeight: 600 }}>
                              INTEGRATION PROVIDERS:
                            </span>
                            <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.3rem' }}>
                              {app.supported_providers.map((p) => (
                                <span
                                  key={p}
                                  style={{
                                    fontSize: '0.7rem',
                                    padding: '0.15rem 0.45rem',
                                    borderRadius: '4px',
                                    backgroundColor: 'rgba(0, 240, 255, 0.1)',
                                    color: '#00F0FF',
                                    border: '1px solid rgba(0, 240, 255, 0.25)',
                                  }}
                                >
                                  {p}
                                </span>
                              ))}
                            </div>
                          </div>

                          {/* Installed Path if available */}
                          {app.installed_path && (
                            <div style={{ marginBottom: '0.8rem', fontSize: '0.72rem', color: '#8993A3' }}>
                              <span style={{ fontWeight: 600 }}>EXECUTABLE PATH: </span>
                              <span style={{ color: '#F1F3F5', fontFamily: 'monospace' }}>
                                {app.installed_path}
                              </span>
                            </div>
                          )}

                          {/* Capabilities Catalog */}
                          <div>
                            <span style={{ fontSize: '0.72rem', color: '#8993A3', fontWeight: 600 }}>
                              SUPPORTED CAPABILITIES ({app.capabilities.length}):
                            </span>
                            <div
                              style={{
                                marginTop: '0.4rem',
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))',
                                gap: '0.5rem',
                              }}
                            >
                              {app.capabilities.map((cap) => (
                                <div
                                  key={cap.id}
                                  style={{
                                    backgroundColor: 'rgba(0, 0, 0, 0.35)',
                                    border: '1px solid rgba(255, 255, 255, 0.06)',
                                    borderRadius: '4px',
                                    padding: '0.5rem 0.7rem',
                                  }}
                                >
                                  <div
                                    style={{
                                      display: 'flex',
                                      justifyContent: 'space-between',
                                      alignItems: 'center',
                                    }}
                                  >
                                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#F1F3F5' }}>
                                      {cap.name}
                                    </span>
                                    <span
                                      style={{
                                        fontSize: '0.65rem',
                                        fontWeight: 700,
                                        padding: '0.1rem 0.35rem',
                                        borderRadius: '3px',
                                        backgroundColor:
                                          cap.permission_level === 'read_only'
                                            ? 'rgba(34, 197, 94, 0.15)'
                                            : cap.permission_level === 'controlled'
                                            ? 'rgba(59, 130, 246, 0.15)'
                                            : cap.permission_level === 'consequential'
                                            ? 'rgba(234, 179, 8, 0.15)'
                                            : 'rgba(239, 68, 68, 0.15)',
                                        color:
                                          cap.permission_level === 'read_only'
                                            ? '#4ade80'
                                            : cap.permission_level === 'controlled'
                                            ? '#60a5fa'
                                            : cap.permission_level === 'consequential'
                                            ? '#facc15'
                                            : '#f87171',
                                      }}
                                    >
                                      {cap.permission_level.toUpperCase()}
                                    </span>
                                  </div>
                                  <div style={{ fontSize: '0.72rem', color: '#B0B7C3', marginTop: '0.2rem' }}>
                                    {cap.description}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            /* Activity Logs Tab */
            <div>
              {activityLogs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem', color: '#8993A3' }}>
                  No integration actions recorded yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {activityLogs.map((log, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '0.6rem 0.8rem',
                        backgroundColor: 'rgba(15, 23, 42, 0.65)',
                        borderLeft: `3px solid ${log.success ? '#00F0FF' : '#ef4444'}`,
                        borderRadius: '4px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.2rem',
                        fontSize: '0.75rem',
                        fontFamily: 'monospace',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8993A3' }}>
                        <span>
                          <strong style={{ color: '#00F0FF' }}>{log.app_id}</strong> &gt; {log.capability_id} ({log.provider})
                        </span>
                        <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <div style={{ color: log.success ? '#F1F3F5' : '#fca5a5' }}>
                        {log.summary}
                      </div>
                      {log.error && <div style={{ color: '#ef4444' }}>Error: {log.error}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Security and Privacy Footer */}
        <div
          style={{
            padding: '0.65rem 1.4rem',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            backgroundColor: 'rgba(5, 10, 20, 0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '0.72rem',
            color: '#8993A3',
          }}
        >
          <div>
            🔒 <strong>Phase 5.2 Security:</strong> Master passwords, raw cookies, and credentials are never stored. Consequential messaging and external communications require explicit operator approval with cryptographic SHA-256 parameter binding.
          </div>
          <button
            onClick={onClose}
            style={{
              padding: '0.35rem 0.85rem',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#F1F3F5',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 600,
            }}
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  );
};
