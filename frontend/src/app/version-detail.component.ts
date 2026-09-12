import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, Detail, Trace, Version } from './api.service';

@Component({
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  template: `
    <ng-container *ngIf="version">
      <h2>
        {{ version.contract_name }} — 公示版本 v{{ version.version_no }}
        <span class="badge" [ngClass]="version.status">{{ version.status_display }}</span>
      </h2>

      <div class="card" *ngIf="trace">
        <h3>收益来源(逐项追溯的起点)</h3>
        <p>合同:{{ trace.contract.name }} ｜ 总额 ¥{{ trace.contract.total_amount }}
           ｜ 归属期 {{ trace.contract.period_start }} ~ {{ trace.contract.period_end }}
           ｜ 收款日期 {{ trace.contract.received_date }}</p>
        <p>适用范围:{{ version.scope_display }}<span *ngIf="version.building_names.length">:{{ version.building_names.join('、') }}</span>
           ｜ 分摊方式:{{ version.method_display }} ｜ 分摊规则 v{{ trace.rule_version }}
           ｜ 分配合计 ¥{{ version.allocated_total }}
           <ng-container *ngIf="+version.unallocated_amount > 0">
             ｜ <span class="remainder">份额不足未分配结余 ¥{{ version.unallocated_amount }}</span>
           </ng-container>
        </p>
        <p *ngIf="version.carry_forward">
          已结转 ¥{{ version.carry_forward.amount }}
          (冻结 ¥{{ version.carry_forward.frozen_total }},
          {{ version.carry_forward.carried_at | date:'yyyy-MM-dd HH:mm' }})
          — 记录只读,仅可追加调整
        </p>
      </div>

      <div class="card">
        <button *ngIf="version.status === 'DRAFT'" (click)="publish()">公示</button>
        <button *ngIf="version.status === 'PUBLISHED'" (click)="carryForward()">结转</button>
        <span class="muted" *ngIf="version.status === 'PUBLISHED'">
          公示期内不可结转;异议部分按冻结金额扣除
        </span>
        <div class="error" *ngIf="error">{{ error }}</div>
      </div>

      <h3>分摊明细</h3>
      <table>
        <thead><tr>
          <th>楼栋</th><th>房号</th><th>业主</th><th>归属片段</th><th>份额</th>
          <th>金额</th><th>冻结</th><th>可付</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr *ngFor="let d of version.details">
            <td>{{ d.building_name }}</td>
            <td>{{ d.unit_code }}</td>
            <td>{{ d.owner_name }}</td>
            <td>{{ d.slice_start }} ~ {{ d.slice_end }}
                <span class="muted">权属#{{ d.ownership_period }}</span></td>
            <td>{{ +d.share * 100 | number:'1.0-4' }}%</td>
            <td>¥{{ d.amount }} <span *ngIf="d.remainder_applied" class="remainder" title="尾差调整">±0.01</span></td>
            <td><span class="frozen" *ngIf="+d.frozen_amount > 0">¥{{ d.frozen_amount }}</span>
                <span *ngIf="+d.frozen_amount === 0">—</span></td>
            <td>¥{{ d.payable }}</td>
            <td>
              <ng-container *ngIf="version.status === 'PUBLISHED'">
                <input [(ngModel)]="disputeAmount[d.id]" placeholder="金额" size="6" />
                <button (click)="dispute(d)">提异议</button>
              </ng-container>
              <ng-container *ngIf="version.status === 'CARRIED'">
                <input [(ngModel)]="adjustDelta[d.id]" placeholder="±金额" size="6" />
                <button (click)="adjust(d)">追加调整</button>
              </ng-container>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="card" *ngIf="hasDisputes()">
        <h3>异议记录</h3>
        <p *ngFor="let d of version.details">
          <span *ngFor="let x of d.disputes">
            {{ d.unit_code }} {{ d.owner_name }}:冻结 ¥{{ x.amount }}({{ x.reason }})<br/>
          </span>
        </p>
      </div>

      <div class="card" *ngIf="hasAdjustments()">
        <h3>追加调整记录(只增不改)</h3>
        <p *ngFor="let d of version.details">
          <span *ngFor="let a of d.adjustments">
            {{ d.unit_code }} {{ d.owner_name }}:{{ a.delta }}({{ a.reason }},
            {{ a.created_at | date:'yyyy-MM-dd HH:mm' }})<br/>
          </span>
        </p>
      </div>
    </ng-container>
  `,
})
export class VersionDetailComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);
  version?: Version;
  trace?: Trace;
  error = '';
  disputeAmount: Record<number, string> = {};
  adjustDelta: Record<number, string> = {};
  private id = 0;

  ngOnInit() {
    this.id = +this.route.snapshot.paramMap.get('id')!;
    this.reload();
  }
  reload() {
    this.api.version(this.id).subscribe((v) => (this.version = v));
    this.api.trace(this.id).subscribe((t) => (this.trace = t));
  }
  private fail(msg: string) { return (e: any) => (this.error = (e.error?.detail || []).join?.(';') || msg); }
  publish() { this.error = ''; this.api.publish(this.id).subscribe({ next: () => this.reload(), error: this.fail('公示失败') }); }
  carryForward() { this.error = ''; this.api.carryForward(this.id, '').subscribe({ next: () => this.reload(), error: this.fail('结转失败') }); }
  dispute(d: Detail) {
    this.error = '';
    this.api.dispute(d.id, this.disputeAmount[d.id] || '0', '业主异议').subscribe({ next: () => this.reload(), error: this.fail('异议失败') });
  }
  adjust(d: Detail) {
    this.error = '';
    this.api.adjust(this.id, d.id, this.adjustDelta[d.id] || '0', '复核调整').subscribe({ next: () => this.reload(), error: this.fail('调整失败') });
  }
  hasDisputes() { return this.version?.details.some((d) => d.disputes.length); }
  hasAdjustments() { return this.version?.details.some((d) => d.adjustments.length); }
}
