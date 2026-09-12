import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiService, Contract, Rule, Version } from './api.service';

@Component({
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <ng-container *ngIf="contract">
      <h2>{{ contract.name }}</h2>
      <div class="card">
        <p>来源:{{ contract.source_type_display }} ｜ 总额:<b>¥{{ contract.total_amount }}</b></p>
        <p>收入归属期:{{ contract.period_start }} ~ {{ contract.period_end }}
           ｜ 收款日期:{{ contract.received_date }}
           <span class="muted">(归属期决定分摊,收款日期仅作记录)</span></p>
        <p>附件:
          <span *ngFor="let a of contract.attachments">{{ a.name }} </span>
          <span *ngIf="!contract.attachments.length" class="remainder">无附件,不能公示</span>
        </p>
        <input type="file" #f />
        <button (click)="upload(f)" [disabled]="!f.files?.length">上传附件</button>
        <div class="error" *ngIf="error">{{ error }}</div>
      </div>

      <h3>分摊规则</h3>
      <table>
        <thead><tr><th>版本</th><th>范围</th><th>方式</th><th>份额不足策略</th><th>公示天数</th><th>状态</th><th></th></tr></thead>
        <tbody>
          <tr *ngFor="let r of rules">
            <td>v{{ r.version_no }}</td>
            <td>{{ r.scope_type === 'ALL' ? '全体业主' : '指定楼栋' }}</td>
            <td>{{ r.method === 'BY_AREA' ? '按面积' : '固定份额' }}</td>
            <td>{{ r.shortfall_policy === 'RESERVE' ? '结余留存' : '按比例放大' }}</td>
            <td>{{ r.publication_days }}</td>
            <td>{{ r.is_active ? '当前有效' : '已作废' }}</td>
            <td><button *ngIf="r.is_active" (click)="generate(r)">生成公示版本</button></td>
          </tr>
        </tbody>
      </table>

      <h3>已生成版本</h3>
      <table>
        <thead><tr><th>版本</th><th>状态</th><th>分配合计</th><th>未分配结余</th><th>生成时间</th><th></th></tr></thead>
        <tbody>
          <tr *ngFor="let v of versions">
            <td>v{{ v.version_no }} (规则v{{ v.rule_version_no }})</td>
            <td><span class="badge" [ngClass]="v.status">{{ v.status_display }}</span></td>
            <td>¥{{ v.allocated_total }}</td>
            <td><span [class.remainder]="+v.unallocated_amount > 0">¥{{ v.unallocated_amount }}</span></td>
            <td>{{ v.computed_at | date:'yyyy-MM-dd HH:mm' }}</td>
            <td><a [routerLink]="['/versions', v.id]">明细</a></td>
          </tr>
        </tbody>
      </table>
    </ng-container>
  `,
})
export class ContractDetailComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  contract?: Contract;
  rules: Rule[] = [];
  versions: Version[] = [];
  error = '';
  private id = 0;

  ngOnInit() {
    this.id = +this.route.snapshot.paramMap.get('id')!;
    this.reload();
  }
  reload() {
    this.api.contract(this.id).subscribe((c) => (this.contract = c));
    this.api.rules().subscribe((rs) => (this.rules = rs.filter((r) => r.contract === this.id)));
    this.api.versions().subscribe((vs) => (this.versions = vs.filter((v) => v.contract_id === this.id)));
  }
  upload(f: HTMLInputElement) {
    const file = f.files?.[0];
    if (!file) return;
    this.api.uploadAttachment(this.id, file, file.name).subscribe({ next: () => this.reload() });
  }
  generate(r: Rule) {
    this.error = '';
    this.api.generate(r.id).subscribe({
      next: () => this.reload(),
      error: (e) => (this.error = (e.error?.detail || []).join?.(';') || '生成失败'),
    });
  }
}
