import React, { useState, useEffect } from 'react';
import { Project, ProjectStatus, BillingMethod } from '../types';
import { Modal } from '../../../components/common/Modal';
import { Button } from '../../../components/common/Button';
import { Input } from '../../../components/common/Input';
import { Select } from '../../../components/common/Select';

interface ProjectFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    name: string;
    customer: string;
    description: string;
    status: ProjectStatus;
    startDate: string;
    endDate: string;
    billingMethod: BillingMethod;
    budget: number;
    notes?: string;
  }) => void;
  initialProject?: Project | null;
  customerSuggestions: string[];
}

export function ProjectFormModal({
  isOpen,
  onClose,
  onSubmit,
  initialProject,
  customerSuggestions,
}: ProjectFormModalProps) {
  const isEditing = Boolean(initialProject);

  const [name, setName] = useState('');
  const [customer, setCustomer] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<ProjectStatus>('active');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [billingMethod, setBillingMethod] = useState<BillingMethod>('fixed_price');
  const [budget, setBudget] = useState('100000');
  const [notes, setNotes] = useState('');

  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (initialProject) {
      setName(initialProject.name);
      setCustomer(initialProject.customer);
      setDescription(initialProject.description || '');
      setStatus(initialProject.status);
      setStartDate(initialProject.startDate || '');
      setEndDate(initialProject.endDate || '');
      setBillingMethod(initialProject.billingMethod || 'fixed_price');
      setBudget(initialProject.budget ? String(initialProject.budget) : '0');
      setNotes(initialProject.notes || '');
    } else {
      setName('');
      setCustomer('');
      setDescription('');
      setStatus('active');
      const today = new Date().toISOString().split('T')[0];
      setStartDate(today);
      const threeMonthsLater = new Date();
      threeMonthsLater.setMonth(threeMonthsLater.getMonth() + 3);
      setEndDate(threeMonthsLater.toISOString().split('T')[0]);
      setBillingMethod('fixed_price');
      setBudget('100000');
      setNotes('');
    }
    setErrors({});
  }, [initialProject, isOpen]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!name.trim()) {
      newErrors.name = 'Project name is required';
    }

    if (!customer.trim()) {
      newErrors.customer = 'Customer name is required';
    }

    const numBudget = parseFloat(budget);
    if (isNaN(numBudget) || numBudget < 0) {
      newErrors.budget = 'Please enter a valid non-negative budget';
    }

    if (startDate && endDate && new Date(endDate) < new Date(startDate)) {
      newErrors.endDate = 'End date cannot be earlier than start date';
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    onSubmit({
      name: name.trim(),
      customer: customer.trim(),
      description: description.trim(),
      status,
      startDate,
      endDate,
      billingMethod,
      budget: numBudget,
      notes: notes.trim(),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Project' : 'Create New Project'}
      description={
        isEditing
          ? 'Update project scope, timelines, billing rates, and budget'
          : 'Define customer engagement terms, timelines, and financial limits'
      }
      size="lg"
      footer={
        <>
          <Button variant="outline" size="sm" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            form="project-form"
          >
            {isEditing ? 'Save Changes' : 'Create Project'}
          </Button>
        </>
      }
    >
      <form id="project-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Project Name */}
          <div className="sm:col-span-2">
            <Input
              label="Project Name"
              required
              placeholder="e.g. Website Revamp, Cloud Infrastructure Migration"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={errors.name}
            />
          </div>

          {/* Customer */}
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Customer <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              list="customer-datalist"
              required
              placeholder="Select or enter customer..."
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            />
            <datalist id="customer-datalist">
              {customerSuggestions.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            {errors.customer && (
              <p className="mt-1 text-xs text-rose-600 font-medium">{errors.customer}</p>
            )}
          </div>

          {/* Billing Method */}
          <div>
            <Select
              label="Billing Method"
              required
              value={billingMethod}
              onChange={(e) => setBillingMethod(e.target.value as BillingMethod)}
              options={[
                { value: 'fixed_price', label: 'Fixed Price' },
                { value: 'time_and_material', label: 'Time & Material' },
                { value: 'non_billable', label: 'Non-Billable (Internal/R&D)' },
              ]}
            />
          </div>

          {/* Project Status */}
          <div>
            <Select
              label="Project Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as ProjectStatus)}
              options={[
                { value: 'draft', label: 'Draft' },
                { value: 'active', label: 'Active' },
                { value: 'on_hold', label: 'On Hold' },
                { value: 'completed', label: 'Completed' },
                { value: 'cancelled', label: 'Cancelled' },
              ]}
            />
          </div>

          {/* Project Budget */}
          <div>
            <Input
              label="Project Budget (₹)"
              type="number"
              min="0"
              step="1000"
              placeholder="e.g. 150000"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              error={errors.budget}
            />
          </div>

          {/* Start Date */}
          <div>
            <Input
              label="Start Date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          {/* End Date */}
          <div>
            <Input
              label="End Date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              error={errors.endDate}
            />
          </div>

          {/* Description */}
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Description
            </label>
            <textarea
              rows={2}
              placeholder="Describe deliverables, key milestones, and business goals..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            />
          </div>

          {/* Notes */}
          <div className="sm:col-span-2">
            <label className="block text-xs font-medium text-slate-700 mb-1.5">
              Internal Notes (Optional)
            </label>
            <textarea
              rows={2}
              placeholder="Any billing constraints, SLA terms, or team instructions..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
            />
          </div>
        </div>
      </form>
    </Modal>
  );
}
